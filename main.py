import json
import os

import requests
import streamlit as st


REALTIME_CLIENT_SECRET_URL = "https://api.openai.com/v1/realtime/client_secrets"


def get_api_key() -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key

    try:
        return st.secrets.get("OPENAI_API_KEY")
    except st.errors.StreamlitSecretNotFoundError:
        return None


def create_client_secret(
    api_key: str,
    model: str,
    voice: str,
    instructions: str,
) -> str:
    response = requests.post(
        REALTIME_CLIENT_SECRET_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "session": {
                "type": "realtime",
                "model": model,
                "instructions": instructions,
                "audio": {
                    "output": {
                        "voice": voice,
                    },
                },
            },
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return data["value"]


def realtime_component(ephemeral_key: str) -> None:
    key_json = json.dumps(ephemeral_key)
    st.components.v1.html(
        f"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{
      margin: 0;
      color: #17202a;
      background: #f7f9fc;
    }}
    .app {{
      display: grid;
      gap: 16px;
      padding: 18px;
      border: 1px solid #d9e2ef;
      border-radius: 8px;
      background: #ffffff;
    }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
    }}
    button {{
      min-width: 112px;
      border: 1px solid #1f6feb;
      border-radius: 7px;
      padding: 10px 14px;
      background: #1f6feb;
      color: #ffffff;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
    }}
    button.secondary {{
      border-color: #bac7d9;
      background: #ffffff;
      color: #17202a;
    }}
    button:disabled {{
      cursor: not-allowed;
      opacity: 0.55;
    }}
    .status {{
      min-height: 24px;
      color: #526071;
      font-size: 14px;
    }}
    .meter {{
      width: 100%;
      height: 10px;
      overflow: hidden;
      border-radius: 999px;
      background: #e7edf5;
    }}
    .level {{
      width: 0%;
      height: 100%;
      background: #20a67a;
      transition: width 80ms linear;
    }}
    .log {{
      height: 220px;
      overflow: auto;
      border: 1px solid #d9e2ef;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfe;
      font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre-wrap;
    }}
    .send {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
    }}
    input {{
      min-width: 0;
      border: 1px solid #bac7d9;
      border-radius: 7px;
      padding: 10px 12px;
      font: inherit;
    }}
    audio {{
      width: 100%;
    }}
  </style>
</head>
<body>
  <div class="app">
    <div class="controls">
      <button id="start">接続</button>
      <button id="stop" class="secondary" disabled>切断</button>
      <span id="status" class="status">未接続</span>
    </div>
    <div class="meter" aria-hidden="true"><div id="level" class="level"></div></div>
    <div class="send">
      <input id="text" placeholder="テキストでも送信できます" />
      <button id="send" class="secondary" disabled>送信</button>
    </div>
    <audio id="remoteAudio" autoplay></audio>
    <div id="log" class="log"></div>
  </div>

  <script>
    const EPHEMERAL_KEY = {key_json};
    const startButton = document.getElementById("start");
    const stopButton = document.getElementById("stop");
    const sendButton = document.getElementById("send");
    const textInput = document.getElementById("text");
    const statusEl = document.getElementById("status");
    const logEl = document.getElementById("log");
    const levelEl = document.getElementById("level");
    const remoteAudio = document.getElementById("remoteAudio");

    let pc = null;
    let dc = null;
    let micStream = null;
    let audioContext = null;
    let meterTimer = null;

    function setStatus(message) {{
      statusEl.textContent = message;
    }}

    function log(message) {{
      const time = new Date().toLocaleTimeString();
      logEl.textContent += `[${{time}}] ${{message}}\\n`;
      logEl.scrollTop = logEl.scrollHeight;
    }}

    function updateControls(connected) {{
      startButton.disabled = connected;
      stopButton.disabled = !connected;
      sendButton.disabled = !connected;
    }}

    function watchMicLevel(stream) {{
      audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      meterTimer = setInterval(() => {{
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((sum, value) => sum + value, 0) / data.length;
        levelEl.style.width = `${{Math.min(100, avg * 1.8)}}%`;
      }}, 90);
    }}

    function handleServerEvent(event) {{
      if (event.type === "response.audio_transcript.delta" && event.delta) {{
        log(`Assistant: ${{event.delta}}`);
      }} else if (event.type === "response.done") {{
        log("応答完了");
      }} else if (event.type === "input_audio_buffer.speech_started") {{
        log("発話を検出");
      }} else if (event.type === "input_audio_buffer.speech_stopped") {{
        log("発話終了");
      }} else if (event.type === "error") {{
        log(`Error: ${{event.error?.message || JSON.stringify(event)}}`);
      }}
    }}

    async function start() {{
      try {{
        setStatus("マイク許可を待っています...");
        pc = new RTCPeerConnection();
        pc.ontrack = (event) => {{
          remoteAudio.srcObject = event.streams[0];
        }};
        pc.onconnectionstatechange = () => {{
          setStatus(`接続状態: ${{pc.connectionState}}`);
          if (["failed", "closed", "disconnected"].includes(pc.connectionState)) {{
            updateControls(false);
          }}
        }};

        micStream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
        micStream.getTracks().forEach((track) => pc.addTrack(track, micStream));
        watchMicLevel(micStream);

        dc = pc.createDataChannel("oai-events");
        dc.addEventListener("open", () => {{
          log("データチャンネル接続");
          updateControls(true);
        }});
        dc.addEventListener("message", (message) => {{
          try {{
            handleServerEvent(JSON.parse(message.data));
          }} catch (error) {{
            log(message.data);
          }}
        }});

        setStatus("Realtime API に接続しています...");
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        const response = await fetch("https://api.openai.com/v1/realtime/calls", {{
          method: "POST",
          body: offer.sdp,
          headers: {{
            "Authorization": `Bearer ${{EPHEMERAL_KEY}}`,
            "Content-Type": "application/sdp",
          }},
        }});

        if (!response.ok) {{
          throw new Error(await response.text());
        }}

        await pc.setRemoteDescription({{
          type: "answer",
          sdp: await response.text(),
        }});
      }} catch (error) {{
        log(`接続エラー: ${{error.message}}`);
        setStatus("接続に失敗しました");
        stop();
      }}
    }}

    function sendText() {{
      const text = textInput.value.trim();
      if (!text || !dc || dc.readyState !== "open") return;
      dc.send(JSON.stringify({{
        type: "conversation.item.create",
        item: {{
          type: "message",
          role: "user",
          content: [{{ type: "input_text", text }}],
        }},
      }}));
      dc.send(JSON.stringify({{ type: "response.create" }}));
      log(`User: ${{text}}`);
      textInput.value = "";
    }}

    function stop() {{
      if (meterTimer) clearInterval(meterTimer);
      if (audioContext) audioContext.close();
      if (micStream) micStream.getTracks().forEach((track) => track.stop());
      if (dc) dc.close();
      if (pc) pc.close();
      meterTimer = null;
      audioContext = null;
      micStream = null;
      dc = null;
      pc = null;
      levelEl.style.width = "0%";
      remoteAudio.srcObject = null;
      updateControls(false);
      setStatus("未接続");
    }}

    startButton.addEventListener("click", start);
    stopButton.addEventListener("click", stop);
    sendButton.addEventListener("click", sendText);
    textInput.addEventListener("keydown", (event) => {{
      if (event.key === "Enter") sendText();
    }});
  </script>
</body>
</html>
        """,
        height=430,
    )


def main() -> None:
    st.set_page_config(page_title="GPT Realtime Voice Bot", page_icon=":microphone:")

    st.title("GPT Realtime Voice Bot")
    st.caption("OpenAI Realtime API と WebRTC を使った Streamlit ボイスボット")

    with st.sidebar:
        st.header("設定")
        model = st.text_input("Model", value="gpt-realtime-2")
        voice = st.selectbox("Voice", ["marin", "cedar"], index=0)
        instructions = st.text_area(
            "System instructions",
            value=(
                "あなたは日本語で自然に会話するボイスボットです。"
                "短く明確に答え、必要に応じて確認質問をしてください。"
            ),
            height=130,
        )
        refresh_secret = st.button("短命キーを再発行")

    api_key = get_api_key()
    if not api_key:
        st.warning(
            "OPENAI_API_KEY が未設定です。環境変数または Streamlit secrets に設定してください。"
        )
        st.stop()

    cache_key = (model, voice, instructions)
    if refresh_secret or st.session_state.get("client_secret_cache_key") != cache_key:
        try:
            st.session_state.client_secret = create_client_secret(
                api_key=api_key,
                model=model,
                voice=voice,
                instructions=instructions,
            )
            st.session_state.client_secret_cache_key = cache_key
        except requests.HTTPError as error:
            detail = error.response.text if error.response is not None else str(error)
            st.error(f"Realtime client secret の発行に失敗しました: {detail}")
            st.stop()
        except requests.RequestException as error:
            st.error(f"OpenAI API への接続に失敗しました: {error}")
            st.stop()

    realtime_component(st.session_state.client_secret)


if __name__ == "__main__":
    main()
