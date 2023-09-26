import asyncio
from pprint import pprint
import time
import queue

from jupyter_client import AsyncKernelManager


async def main():
    km = AsyncKernelManager(kernel_name='hexe-python-kernel')
    await km.start_kernel()

    kc = km.client()
    kc.start_channels()

    print('execute')
    msg_id = kc.execute('import matplotlib.pyplot as plt\n\nplt.barh(["hello", "world"], [200, 230])\nplt.show()')
    #msg_id = kc.execute('echo "hello world"')

    print('msg_id:', msg_id)

    try:
        while True:
            try:
                print('get_iopub_msg')
                msg = await kc.get_iopub_msg()
            except queue.Empty:
                continue

            if msg.get("parent_header", {}).get("msg_id") == msg_id:
                if msg['msg_type'] == 'stream':
                    print(msg['content']['text'])
                elif msg['msg_type'] == 'execute_result':
                    print(f"[{msg['content']['execution_count']}] {msg['content']['data']['text/plain']}")
                elif msg['msg_type'] == 'status' and msg['content']['execution_state'] == 'idle':
                    break
                elif msg['msg_type'] == 'error':
                    pprint(msg['content'])
                else:
                    pprint(msg)
            else:
                print('unknown:', msg)
    finally:
        kc.stop_channels()
        print('shutdown...')
        await km.shutdown_kernel()


asyncio.run(main())
