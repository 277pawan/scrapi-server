from uvicorn import run
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import List

from src.crawl_url import crawl_url, scrape_urls_api


# from crawler.message_broker.sub_broker import receive_task_fetch_link


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Crawler UI</title>
        <style>
            body { font-family: sans-serif; padding: 20px; }
            #status { padding: 10px; margin-bottom: 20px; border-radius: 5px; background: #eee; }
            .connected { background: #d4edda !important; color: #155724; }
            .disconnected { background: #f8d7da !important; color: #721c24; }
            pre { background: #f4f4f4; padding: 10px; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; max-height: 400px; overflow-y: auto; }
        </style>
    </head>
    <body>
        <h1>Universal Crawler UI</h1>
        <div id="status" class="disconnected">WebSocket Status: Disconnected</div>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off" placeholder="Enter URLs separated by commas" style="width: 80%; padding: 8px;"/>
            <button style="padding: 8px;">Crawl</button>
        </form>
        <h2>Results:</h2>
        <ul id='messages' style="list-style-type: none; padding: 0;">
        </ul>
        <script>
            let ws;
            function connect() {
                ws = new WebSocket("ws://127.0.0.1:8001/ws");
                
                ws.onopen = function() {
                    let status = document.getElementById('status');
                    status.textContent = "WebSocket Status: CONNECTED";
                    status.className = "connected";
                };

                ws.onmessage = function(event) {
                    console.log("Received data from server! Size: " + event.data.length + " bytes.");
                    let messages = document.getElementById('messages');
                    let li = document.createElement('li');
                    li.style.cssText = 'margin-bottom: 20px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;';
                    
                    let textToCopy = event.data;
                    let displayText = event.data;
                    
                    try {
                        let parsed = JSON.parse(event.data);
                        textToCopy = parsed.markdown || event.data;
                        displayText = JSON.stringify(parsed, null, 2);
                    } catch (e) {}
                    
                    // Header bar with URL label + copy button
                    let header = document.createElement('div');
                    header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; background: #2d2d2d; color: #eee; padding: 8px 12px; font-size: 13px;';
                    
                    let label = document.createElement('span');
                    try { label.textContent = '🌐 ' + JSON.parse(event.data).url; } catch(e) { label.textContent = '🌐 Response'; }
                    
                    let copyBtn = document.createElement('button');
                    copyBtn.textContent = '📋 Copy Markdown';
                    copyBtn.style.cssText = 'background: #4CAF50; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px;';
                    copyBtn.onclick = function() {
                        navigator.clipboard.writeText(textToCopy).then(() => {
                            copyBtn.textContent = '✅ Copied!';
                            setTimeout(() => { copyBtn.textContent = '📋 Copy Markdown'; }, 2000);
                        }).catch(() => {
                            // Fallback for older browsers
                            let ta = document.createElement('textarea');
                            ta.value = textToCopy;
                            document.body.appendChild(ta);
                            ta.select();
                            document.execCommand('copy');
                            document.body.removeChild(ta);
                            copyBtn.textContent = '✅ Copied!';
                            setTimeout(() => { copyBtn.textContent = '📋 Copy Markdown'; }, 2000);
                        });
                    };
                    
                    header.appendChild(label);
                    header.appendChild(copyBtn);
                    li.appendChild(header);
                    
                    let pre = document.createElement('pre');
                    pre.style.cssText = 'margin: 0; max-height: 400px; overflow-y: auto;';
                    pre.textContent = displayText;
                    li.appendChild(pre);
                    
                    // Insert at top
                    messages.insertBefore(li, messages.firstChild);
                };

                ws.onclose = function(e) {
                    let status = document.getElementById('status');
                    status.textContent = "WebSocket Status: DISCONNECTED (Server might have reloaded or crashed)";
                    status.className = "disconnected";
                    console.error("WebSocket closed. Reconnecting in 2 seconds...");
                    setTimeout(connect, 2000);
                };
                
                ws.onerror = function(err) {
                    console.error("WebSocket encountered error: ", err, "Closing socket");
                    ws.close();
                };
            }

            connect();

            function sendMessage(event) {
                event.preventDefault();
                let input = document.getElementById("messageText");
                let urls = input.value.split(",").map(item => item.trim()).filter(Boolean);
                
                if (ws.readyState === WebSocket.OPEN) {
                    console.log("Sending URLs to server:", urls);
                    ws.send(JSON.stringify(urls));
                    
                    let messages = document.getElementById('messages');
                    let li = document.createElement('li');
                    li.innerHTML = `<i>Sent request to crawl: ${urls.join(', ')}... waiting for response...</i>`;
                    messages.insertBefore(li, messages.firstChild);
                    
                    input.value = '';
                } else {
                    alert("WebSocket is not connected! Please wait or refresh the page.");
                }
            }
        </script>
    </body>
</html>
"""


# @app.get("/")
# async def health_check():
#     return JSONResponse(
#         status_code=200,
#         content={"status": "running"}
#     )

@app.get("/")
async def get():
    return HTMLResponse(html)

class ScrapeRequest(BaseModel):
    urls: List[str]

@app.post("/api/scrape")
async def scrape_api(request: ScrapeRequest):
    """
    API endpoint for sending an array of links.
    Returns a dictionary mapping URLs to their scraped data.
    """
    results = await scrape_urls_api(request.urls)
    return JSONResponse(content={"status": "success", "data": results})

from fastapi import WebSocketDisconnect

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            await crawl_url(data, websocket)
            await websocket.send_text(f"Message text was: {data}")
    except WebSocketDisconnect:
        print("Client disconnected from WebSocket.")
    except Exception as e:
        print(f"WebSocket error: {e}")