import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from jupyter_client import AsyncKernelClient, AsyncKernelManager
from jupyter_client.kernelspec import KernelSpec, KernelSpecManager

import event


class HexeKernelSpecManager(KernelSpecManager):
    def __init__(self, user_id: str) -> None:
        self.__user_id = user_id

    def get_kernel_spec(self, kernel_name: str) -> KernelSpec:
        kernel_name = kernel_name.replace("hexe-", "")

        return KernelSpec(
            display_name=kernel_name,
            language=kernel_name,
            argv=[
                "docker",
                "run",
                "--network=host",
                "--rm",
                "-v",
                "{connection_file}:/connection_file",
                f"hexe-{kernel_name}-kernel",
            ],
        )


class CodeRunner:
    km: AsyncKernelManager
    kc: AsyncKernelClient | None = None

    def __init__(self, user_id: str, language: str) -> None:
        self.user_id = user_id
        self.language = language

        self.km = AsyncKernelManager(
            kernel_name=f"hexe-{language}",
            kernel_spec_manager=HexeKernelSpecManager(user_id),
        )

    async def _start(self) -> AsyncKernelClient:
        if self.kc is not None:
            return self.kc
        else:
            await self.km.start_kernel()

            self.kc = self.km.client()
            self.kc.start_channels()

            return self.kc

    async def shutdown(self) -> None:
        if self.kc is not None:
            self.kc.stop_channels()

        await self.km.shutdown_kernel()

    async def execute(
        self, source: uuid.UUID, code: str
    ) -> AsyncIterator[event.FunctionOutput | event.Error]:
        if self.kc is None:
            self.kc = await self._start()

        stream_id = uuid.uuid4()
        stime = datetime.now()

        msg_id = self.kc.execute(code)

        content = ""
        result: event.FunctionOutput | None = None

        while True:
            print("waiting...")
            msg = await self.kc.get_iopub_msg()
            print("got message", msg)

            if msg.get("parent_header", {}).get("msg_id") == msg_id:
                if msg["msg_type"] == "error":
                    yield event.Error(
                        id=uuid.uuid4(),
                        source=source,
                        content=msg["content"]["evalue"],
                    )

                if msg["msg_type"] == "stream":
                    content += msg["content"]["text"]
                    yield event.FunctionOutput(
                        id=stream_id,
                        name="run_code",
                        content=msg["content"]["text"],
                        source=source,
                        delta=True,
                        created_at=stime,
                    )

                if msg["msg_type"] == "display_data":
                    if "text/html" in msg["content"]["data"]:
                        yield event.FunctionOutput(
                            id=uuid.uuid4(),
                            name="run_code",
                            content=msg["content"]["data"]["text/html"],
                            source=source,
                            created_at=datetime.now(),
                        )
                        continue

                    if "application/json" in msg["content"]["data"]:
                        yield event.FunctionOutput(
                            id=uuid.uuid4(),
                            name="run_code",
                            content="```json\n"
                            + msg["content"]["data"]["application/json"]
                            + "\n```",
                            source=source,
                            created_at=datetime.now(),
                        )
                        continue

                    videotype = [
                        x
                        for x in msg["content"]["data"].keys()
                        if x.startswith("video/")
                    ]
                    if len(videotype) > 0:
                        usetype = videotype[0]
                        if "video/mp4" in videotype:
                            usetype = "video/mp4"

                        alt = (
                            msg["content"]["data"]
                            .get("text/plain", "")
                            .replace('"', "&quot;")
                        )

                        yield event.FunctionOutput(
                            id=uuid.uuid4(),
                            name="run_code",
                            content=(
                                "<video"
                                f" src=\"data:{usetype};base64,{msg['content']['data'][usetype]}\""
                                f' controls="controls" alt="{alt}" />'
                            ),
                            source=source,
                            created_at=datetime.now(),
                        )
                        continue

                    imgtype = [
                        x
                        for x in msg["content"]["data"].keys()
                        if x.startswith("image/")
                    ]
                    if len(imgtype) > 0:
                        usetype = imgtype[0]
                        if "image/svg+xml" in imgtype:
                            usetype = "image/svg+xml"
                        if "image/png" in imgtype:
                            usetype = "image/png"
                        if "image/jpeg" in imgtype:
                            usetype = "image/jpeg"

                        alt = (
                            msg["content"]["data"]
                            .get("text/plain", "")
                            .replace('"', "&quot;")
                        )

                        yield event.FunctionOutput(
                            id=uuid.uuid4(),
                            name="run_code",
                            content=(
                                "<img"
                                f" src=\"data:{usetype};base64,{msg['content']['data'][usetype]}\""
                                f' alt="{alt}" />'
                            ),
                            source=source,
                            created_at=datetime.now(),
                        )
                        continue

                    yield event.FunctionOutput(
                        id=uuid.uuid4(),
                        name="run_code",
                        content="```json\n"
                        + json.dumps(msg["content"]["data"], sort_keys=True, indent=4)
                        + "\n```",
                        source=source,
                        created_at=datetime.now(),
                    )

                if msg["msg_type"] == "execute_result":
                    result = event.FunctionOutput(
                        id=uuid.uuid4(),
                        name="run_code",
                        content=msg["content"]["data"]["text/plain"],
                        source=source,
                        created_at=datetime.now(),
                    )

                if (
                    msg["msg_type"] == "status"
                    and msg["content"]["execution_state"] == "idle"
                ):
                    if content != "":
                        yield event.FunctionOutput(
                            id=stream_id,
                            name="run_code",
                            content=content,
                            source=source,
                            created_at=stime,
                        )
                    if result is not None:
                        yield result
                    return
