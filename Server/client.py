import asyncio
import websockets

from protocol import (
    MessageType,
    ProtocolError,
    decode,
    encode,
    make_auth,
    make_cancel_play,
    make_login,
    make_move,
    make_play,
    make_room_create,
    make_room_join,
)


def parse_user_move(user_input: str):
    cleaned = user_input.replace(",", " ")
    parts = cleaned.split()
    if len(parts) != 4:
        raise ValueError("use: start_row start_col end_row end_col  (e.g. 6 4 4 4)")
    try:
        start_row, start_col, end_row, end_col = (int(p) for p in parts)
    except ValueError as exc:
        raise ValueError("all coordinates must be integers") from exc
    return (start_row, start_col), (end_row, end_col)


def _on_login_ok(data: dict, session: dict) -> None:
    session["token"] = data.get("token")
    session["user_id"] = data.get("user_id")
    print(
        f"\n[CLIENT] Login OK as: {data.get('username')} "
        f"(user_id={data.get('user_id')}, ELO={data.get('elo')})"
    )
    print(f"[CLIENT] Token: {session['token']}")


def _on_auth_ok(data: dict, session: dict) -> None:
    print(
        f"\n[CLIENT] Auth OK: {data.get('username')} "
        f"(ELO={data.get('elo')})"
    )


def _on_room_created(data: dict, session: dict) -> None:
    print(
        f"\n[CLIENT] Room created: {data.get('room_id')} "
        f"(you are {data.get('color')})"
    )


def _on_room_joined(data: dict, session: dict) -> None:
    print(
        f"\n[CLIENT] Joined room {data.get('room_id')} "
        f"as {data.get('role')}"
    )


def _on_rejoined_room(data: dict, session: dict) -> None:
    print(
        f"\n[CLIENT] Rejoined room {data.get('room_id')} "
        f"as {data.get('color')}"
    )


def _on_play_queued(data: dict, session: dict) -> None:
    print(f"\n[CLIENT] Looking for opponent... ({data.get('status')})")


def _on_match_found(data: dict, session: dict) -> None:
    print(
        f"\n[CLIENT] Match found! room={data.get('room_id')} "
        f"color={data.get('color')}"
    )


def _on_match_timeout(data: dict, session: dict) -> None:
    print(f"\n[CLIENT] Matchmaking timeout: {data.get('reason')}")


def _on_disconnect_countdown(data: dict, session: dict) -> None:
    print(
        f"\n[CLIENT] Disconnect countdown: "
        f"{data.get('seconds_left')}s "
        f"(user={data.get('user_id')})"
    )


def _on_ack(data: dict, session: dict) -> None:
    print(
        f"\n[CLIENT] Move accepted: "
        f"{data.get('start')} -> {data.get('end')}"
    )


def _on_state(data: dict, session: dict) -> None:
    print(
        f"\n[CLIENT] State | score={data.get('score')} "
        f"game_over={data.get('game_over')} "
        f"pieces={len(data.get('pieces', []))}"
    )


def _on_game_over(data: dict, session: dict) -> None:
    print(f"\n[CLIENT] GAME OVER! Winner: {data.get('winner')}")
    print(f"[CLIENT] New ratings: {data.get('ratings')}")


def _on_error(data: dict, session: dict) -> None:
    print(f"\n[CLIENT] Error: {data.get('reason')}")


def _on_welcome(data: dict, session: dict) -> None:
    print(
        f"\n[CLIENT] Welcome! You are: {data.get('color')} "
        f"(players: {data.get('player_count')})"
    )


_MESSAGE_HANDLERS = {
    MessageType.LOGIN_OK.value: _on_login_ok,
    MessageType.AUTH_OK.value: _on_auth_ok,
    MessageType.ROOM_CREATED.value: _on_room_created,
    MessageType.ROOM_JOINED.value: _on_room_joined,
    MessageType.REJOINED_ROOM.value: _on_rejoined_room,
    MessageType.PLAY_QUEUED.value: _on_play_queued,
    MessageType.MATCH_FOUND.value: _on_match_found,
    MessageType.MATCH_TIMEOUT.value: _on_match_timeout,
    MessageType.DISCONNECT_COUNTDOWN.value: _on_disconnect_countdown,
    MessageType.ACK.value: _on_ack,
    MessageType.STATE.value: _on_state,
    MessageType.GAME_OVER.value: _on_game_over,
    MessageType.ERROR.value: _on_error,
    MessageType.WELCOME.value: _on_welcome,
}


async def listen_to_server(websocket, session: dict):
    try:
        async for raw in websocket:
            try:
                data = decode(raw)
            except ProtocolError as exc:
                print(f"\n[CLIENT] Bad message: {exc} ({raw})")
                continue

            msg_type = data.get("type")
            handler = _MESSAGE_HANDLERS.get(msg_type)
            if handler is None:
                print(f"\n[CLIENT] Received: {data}")
            else:
                handler(data, session)
    except websockets.exceptions.ConnectionClosed:
        print("\n[CLIENT] Connection closed by server.")


async def start_client():
    uri = "ws://localhost:8765"
    session: dict = {"token": None, "user_id": None}

    try:
        async with websockets.connect(uri) as websocket:
            print("[CLIENT] Connected.")
            print("[CLIENT] Commands after login:")
            print("  play              — queue for matchmaking (±100 ELO)")
            print("  cancel            — leave matchmaking queue")
            print("  create            — create a room")
            print("  join <room_id>    — join / spectate a room")
            print("  <r c r c>         — make a move, e.g. 6 4 4 4")
            print("  exit              — quit\n")

            listener = asyncio.create_task(listen_to_server(websocket, session))

            username = (await asyncio.to_thread(input, "Username: ")).strip()
            if not username:
                print("[CLIENT] Username required.")
                return
            password = await asyncio.to_thread(input, "Password: ")
            if not password:
                print("[CLIENT] Password required.")
                return

            await websocket.send(encode(make_login(username, password)))
            await asyncio.sleep(0.3)

            try:
                while True:
                    user_input = await asyncio.to_thread(input, "Command: ")
                    text = user_input.strip()
                    if not text:
                        continue
                    lower = text.lower()

                    if lower == "exit":
                        print("[CLIENT] Closing...")
                        break
                    if lower == "play":
                        await websocket.send(encode(make_play()))
                        continue
                    if lower == "cancel":
                        await websocket.send(encode(make_cancel_play()))
                        continue
                    if lower == "create":
                        await websocket.send(encode(make_room_create()))
                        continue
                    if lower.startswith("join "):
                        room_id = text.split(maxsplit=1)[1].strip()
                        await websocket.send(encode(make_room_join(room_id)))
                        continue
                    if lower.startswith("auth "):
                        token = text.split(maxsplit=1)[1].strip()
                        await websocket.send(encode(make_auth(token)))
                        continue

                    try:
                        start, end = parse_user_move(text)
                    except ValueError as exc:
                        print(f"[CLIENT] Invalid input: {exc}\n")
                        continue

                    payload = encode(make_move(start, end))
                    print(f"[CLIENT] Sending: {payload}")
                    await websocket.send(payload)
            finally:
                listener.cancel()

    except ConnectionRefusedError:
        print("[CLIENT] Could not connect. Is the server running?")
    except Exception as e:
        print(f"[CLIENT] Error: {e}")


if __name__ == "__main__":
    asyncio.run(start_client())
