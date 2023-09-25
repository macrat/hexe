import uuid
from typing import AsyncIterator
import json
from datetime import datetime

from jupyter_client import AsyncKernelManager, AsyncKernelClient

import event


class CodeRunner:
    km: AsyncKernelManager
    kc: AsyncKernelClient | None = None

    def __init__(self, kernel_name: str) -> None:
        self.kernel_name = kernel_name

        self.km = AsyncKernelManager(kernel_name=self.kernel_name)

    async def start(self) -> None:
        if self.kc is None:
            await self.km.start_kernel()

            self.kc = self.km.client()
            self.kc.start_channels()

    async def shutdown(self) -> None:
        if self.kc is not None:
            self.kc.stop_channels()

        await self.km.shutdown_kernel()

    async def execute(
        self, source: uuid.UUID, code: str
    ) -> AsyncIterator[event.FunctionOutput | event.Error]:
        if self.kc is None:
            raise RuntimeError("Kernel is not running")

        stream_id = uuid.uuid4()
        stime = datetime.now()

        msg_id = self.kc.execute(code)

        content = ""

        while True:
            msg = await self.kc.get_iopub_msg()

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
                        complete=False,
                        created_at=stime,
                    )

                if msg["msg_type"] == "display_data":
                    if "text/html" in msg["content"]["data"]:
                        yield event.FunctionOutput(
                            id=uuid.uuid4(),
                            name="run_code",
                            content=msg["content"]["data"]["text/html"],
                            source=source,
                            complete=True,
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
                            complete=True,
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
                            content=f'<video src="data:{usetype};base64,{msg["content"]["data"][usetype]}" controls="controls" alt="{alt}" />',
                            source=source,
                            complete=True,
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
                            content=f'<img src="data:{usetype};base64,{msg["content"]["data"][usetype]}" alt="{alt}" />',
                            source=source,
                            complete=True,
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
                        complete=True,
                        created_at=datetime.now(),
                    )

                if msg["msg_type"] == "execute_result":
                    yield event.FunctionOutput(
                        id=uuid.uuid4(),
                        name="run_code",
                        content=msg["content"]["data"]["text/plain"],
                        source=source,
                        complete=True,
                        created_at=datetime.now(),
                    )
                    return

                if (
                    msg["msg_type"] == "status"
                    and msg["content"]["execution_state"] == "idle"
                ):
                    yield event.FunctionOutput(
                        id=stream_id,
                        name="run_code",
                        content=content,
                        source=source,
                        complete=True,
                        created_at=stime,
                    )
                    return
