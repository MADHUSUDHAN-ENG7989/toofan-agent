import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="VPL Auto Solver Backend")

# Create static dir if it doesn't exist
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

DEFAULT_API_KEY = os.environ.get("DEFAULT_GEMINI_API_KEY", "YOUR_API_KEY_HERE")
default_key_lock = asyncio.Lock()

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

async def run_automation_process(websocket: WebSocket, username, password, api_key, target_assignment):
    await websocket.send_text("[+] Configuration received. Initializing Playwright Headless Browser...")
    
    # Start subprocess for the automation script
    cmd = ["python", "-u", "solve_programs.py",
           "--username", username,
           "--password", password,
           "--api-key", api_key]
           
    if target_assignment and target_assignment.strip():
        cmd.extend(["--target", target_assignment.strip()])
        
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    async def read_stdout():
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            try:
                await websocket.send_text(line.decode().rstrip())
            except WebSocketDisconnect:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                break

    async def listen_for_stop():
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("action") == "stop":
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                    break
        except WebSocketDisconnect:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

    stdout_task = asyncio.create_task(read_stdout())
    stop_task = asyncio.create_task(listen_for_stop())
    
    done, pending = await asyncio.wait(
        [stdout_task, stop_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    
    for task in pending:
        task.cancel()
        
    await process.wait()
    try:
        await websocket.send_text(f"\n[✓] Automation complete! (Process exited with code {process.returncode})")
        await websocket.close()
    except Exception:
        pass

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        # Wait for configuration message from frontend
        data = await websocket.receive_json()
        username = data.get("username")
        password = data.get("password")
        api_key = data.get("apiKey")
        target_assignment = data.get("targetAssignment")
        
        if not username or not password:
            await websocket.send_text("[-] Missing credentials. Cannot start.")
            await websocket.close()
            return
            
        if not api_key:
            if default_key_lock.locked():
                await websocket.send_text("[!] The shared API key is currently in use.")
                await websocket.send_text("[!] You are placed in a queue. To skip the queue, refresh and paste your own Gemini API key.")
            
            async with default_key_lock:
                await websocket.send_text("[+] Ready to use the shared API key.")
                await run_automation_process(websocket, username, password, DEFAULT_API_KEY, target_assignment)
        else:
            # User provided their own key, run immediately
            await run_automation_process(websocket, username, password, api_key, target_assignment)
            
    except WebSocketDisconnect:
        print("Client disconnected. You may need to manually terminate the process if it's still running.")
    except Exception as e:
        try:
            await websocket.send_text(f"\n[!] Server Error: {str(e)}")
            await websocket.close()
        except:
            pass
