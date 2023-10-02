import uuid
from zoneinfo import ZoneInfo

import event
from history import HistoryDB
from note import NoteDB
from thread import Thread


async def debug_event_handler(ev: event.Event) -> None:
    if isinstance(ev, event.User) and not ev.delta:
        print(f"\nUser:\n{ev.content}\n")
    if isinstance(ev, event.Assistant) and not ev.delta:
        print(f"\nAssistant:\n{ev.content}\n")
    if isinstance(ev, event.FunctionCall) and not ev.delta:
        print(f"\nFunction call: {ev.name}({ev.arguments})\n")
    if isinstance(ev, event.FunctionOutput) and not ev.delta:
        print(f"\nFunction output: {ev.name}\n{ev.content}\n")
    if isinstance(ev, event.Error) and not ev.delta:
        print(f"\nError: {ev.content}\n")


async def debug_main() -> None:
    import sys

    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <message>")
        return

    ns = uuid.uuid5(uuid.NAMESPACE_DNS, "notes")
    notes = NoteDB("./notes", ns)
    history = HistoryDB("./history.db")

    thread = Thread("user1", history, notes, timezone=ZoneInfo("Asia/Tokyo"))

    thread.event_handlers.append(debug_event_handler)

    await thread.send_message(sys.argv[1])

    await thread.shutdown()


async def debug_jupyter() -> None:
    from coderunner import CodeRunner

    r = CodeRunner("user1", "_python")

    async for ev in r.execute(uuid.uuid4(), "import matplotlib.pyplot as plt"):
        await debug_event_handler(ev)

    async for ev in r.execute(uuid.uuid4(), "plt.plot([1, 2, 3, 4])\nplt.show()"):
        await debug_event_handler(ev)

    await r.shutdown()


if __name__ == "__main__":
    import asyncio

    asyncio.run(debug_main())
