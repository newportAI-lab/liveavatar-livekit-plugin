"""Run with FACEMARKET_API_KEY, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET set."""

import os

from livekit.agents import AgentSession

from livekit import agents
from livekit.plugins import facemarket


async def entrypoint(ctx: agents.JobContext) -> None:
    await ctx.connect()
    session = AgentSession()
    previous_session_id = os.getenv("FACEMARKET_PREVIOUS_SESSION_ID") or None
    avatar = facemarket.AvatarSession(
        avatar_id=os.environ["FACEMARKET_AVATAR_ID"],
        sandbox=os.getenv("FACEMARKET_SANDBOX", "").lower() == "true",
    )

    @avatar.on(facemarket.SESSION_READY)
    async def on_ready(event: facemarket.DataChannelEvent) -> None:
        print(f"Renderer ready: {event.participant_identity}")

    @avatar.on(facemarket.ERROR)
    async def on_error(event: facemarket.DataChannelEvent) -> None:
        print(f"Renderer error: {event.data}")

    # Use None for a new platform session; persist avatar.session_id for explicit reconnect.
    await avatar.start(session, room=ctx.room, session_id=previous_session_id)
    print(f"Facemarket session ID: {avatar.session_id}")
    await session.start(agents.Agent(instructions="Be helpful."), room=ctx.room)

    # Call this only when the remote Facemarket session should end.
    await avatar.stop()


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
