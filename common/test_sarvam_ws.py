import asyncio
import websockets
import json
import os
import base64

async def test_sarvam_ws():
    api_key = None
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("SARVAM_API_KEY="):
                    api_key = line.strip().split("=", 1)[1].strip('"').strip("'")
                    break
    
    if not api_key:
        print("SARVAM_API_KEY not found in .env")
        return
        
    uri = "wss://api.sarvam.ai/text-to-speech/ws"
    
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri, additional_headers={"api-subscription-key": api_key}) as ws:
            print("Connected!")
            
            config = {
                "text": "Hello world",
                "model": "bulbul:v3",
                "target_language_code": "en-IN",
                "speaker": "ratan",
                "pace": 1.05,
                "output_audio_codec": "pcm",
                "speech_sample_rate": 16000
            }
            print(f"Sending audio JSON config...")
            await ws.send(json.dumps(config))
            
            # 2. Wait for response
            response = await ws.recv()
            print(f"Response (first 100 chars): {str(response)[:100]}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_sarvam_ws())
