import os
import io
from flask import Flask, request, jsonify, render_template
import requests
import speech_recognition as sr

app = Flask(__name__)

# Replace with your actual ElevenLabs API key
ELEVENLABS_API_KEY = 'sk_c03471a47b86a157c841708a0faa92f356c7668ae94e50b5'

# Assumed ElevenLabs API endpoints (adjust if necessary)
VOICE_CLONE_URL = "https://api.elevenlabs.io/v1/voices/add"
AGENT_CREATE_URL = "https://api.elevenlabs.io/v1/convai/agents/create"
KB_UPLOAD_URL = "https://api.elevenlabs.io/v1/convai/knowledge-base"
AGENT_UPDATE_URL_TEMPLATE = "https://api.elevenlabs.io/v1/convai/agents/{}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/clone-voice', methods=['POST'])
def clone_voice():
    """
    Receives two files from the client:
      - 'voice_sample': the audio sample to clone the user's voice
      - 'role_audio': the audio sample where the user describes the agent's role (system prompt)
    
    This endpoint:
      1. Clones the voice via the ElevenLabs API.
      2. Converts the role audio to text (system prompt) using SpeechRecognition.
      3. Creates a new conversational agent with the cloned voice, system prompt,
         flash model, and RAG enabled.
      4. Returns the created agent_id and other details.
    """
    if 'voice_sample' not in request.files or 'role_audio' not in request.files:
        return jsonify({"error": "Missing voice_sample or role_audio file."}), 400

    voice_file = request.files['voice_sample']
    role_audio_file = request.files['role_audio']

    # Read files into in-memory byte streams
    voice_bytes = io.BytesIO(voice_file.read())
    role_audio_bytes = io.BytesIO(role_audio_file.read())

    # --------- Step 1: Clone Voice via ElevenLabs API ---------
    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    # Use "files" (plural) as the key and pass remove_background_noise as string "false"
    files_payload = {"files": ("sample.wav", voice_bytes, "audio/wav")}
    data_payload = {"name": "UserClonedVoice", "remove_background_noise": "false"}

    clone_response = requests.post(VOICE_CLONE_URL, headers=headers, files=files_payload, data=data_payload)
    if clone_response.status_code != 200:
        return jsonify({"error": "Voice cloning failed", "details": clone_response.text}), 400
    clone_data = clone_response.json()
    cloned_voice_id = clone_data.get("voice_id")
    if not cloned_voice_id:
        return jsonify({"error": "Voice cloning did not return voice_id", "details": clone_data}), 400

    # --------- Step 2: Convert Role Audio to Text (System Prompt) ---------
    recognizer = sr.Recognizer()
    try:
        # Rewind the stream
        role_audio_bytes.seek(0)
        # Convert the file to PCM WAV using pydub
        from pydub import AudioSegment
        audio_segment = AudioSegment.from_file(role_audio_bytes)
        converted_audio = io.BytesIO()
        audio_segment.export(converted_audio, format="wav")
        converted_audio.seek(0)
        # Now use SpeechRecognition on the converted WAV
        with sr.AudioFile(converted_audio) as source:
            audio_data = recognizer.record(source)
        system_prompt = recognizer.recognize_google(audio_data, language="nl-NL")
    except Exception as e:
        print("Error in speech recognition:", e)
        system_prompt = "Default system prompt"
    
    print("System prompt:", system_prompt)

    # --------- Step 3: Create Conversational Agent ---------
    agent_payload = {
        "name": "RAAIT Cloned Agent",
        "conversation_config": {
            "tts": {
                "model_id": "eleven_flash_v2_5",
                "voice_id": cloned_voice_id
            },
            "agent": {
                "language": "nl",
                "prompt": {
                    "prompt": system_prompt,
                    "knowledge_base": [],
                    "rag": {
                        "enabled": True,
                        "embedding_model": "e5_mistral_7b_instruct"
                    }
                }
            }
        },
        "platform_settings": {
            "widget": {
                "variant": "full"
            }
        }
    }

    agent_response = requests.post(AGENT_CREATE_URL, headers={**headers, "Content-Type": "application/json"}, json=agent_payload)
    if agent_response.status_code != 200:
        return jsonify({"error": "Agent creation failed", "details": agent_response.text}), 400

    agent_data = agent_response.json()
    agent_id = agent_data.get("agent_id")
    if not agent_id:
        return jsonify({"error": "Agent creation did not return agent_id", "details": agent_data}), 400

    return jsonify({
        "agent_id": agent_id,
        "system_prompt": system_prompt,
        "cloned_voice_id": cloned_voice_id
    })

@app.route('/api/upload-doc', methods=['POST'])
def upload_doc():
    agent_id = request.form.get("agent_id")
    if not agent_id:
        return jsonify({"error": "Missing agent_id"}), 400

    if 'pdf_file' not in request.files:
        return jsonify({"error": "Missing pdf_file"}), 400
    pdf_file = request.files['pdf_file']

    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    # Use the endpoint as in the playground example
    KB_UPLOAD_URL = "https://api.elevenlabs.io/v1/convai/knowledge-base"
    
    # Use a list of tuples for the file upload
    files_payload = [
        ('file', (pdf_file.filename, pdf_file.stream, "application/pdf"))
    ]
    
    kb_response = requests.post(KB_UPLOAD_URL, headers=headers, files=files_payload)
    print("KB upload status:", kb_response.status_code)
    print("KB upload response:", kb_response.text)
    if kb_response.status_code != 200:
        return jsonify({"error": "Knowledge base upload failed", "details": kb_response.text}), 400

    kb_data = kb_response.json()
    document_id = kb_data.get("id")
    if not document_id:
        return jsonify({"error": "Knowledge base upload did not return document_id", "details": kb_data}), 400

    # Attach the document to the agent:
    # Wrap the document_id in a dictionary to satisfy the KnowledgeBaseLocator model.
    attach_url = AGENT_UPDATE_URL_TEMPLATE.format(agent_id)
    attach_url = AGENT_UPDATE_URL_TEMPLATE.format(agent_id)
    attach_payload = {
        "conversation_config": {
            "agent": {
                "prompt": {
                    "knowledge_base": [
                        {
                            "id": document_id,
                            "type": "file",      # Added required field
                            "name": "Document",
                            "url": f"https://elevenlabs.io/app/conversational-ai/knowledge-base/{document_id}"
                        }
                    ]
                }
            }
        }
    }
    attach_response = requests.patch(
        attach_url,
        headers={**headers, "Content-Type": "application/json"},
        json=attach_payload
    )
    print("Attach doc status:", attach_response.status_code)
    print("Attach doc response:", attach_response.text)
    if attach_response.status_code not in (200, 204):
        return jsonify({"error": "Failed to attach document to agent", "details": attach_response.text}), 400

    return jsonify({"message": "Document uploaded and attached", "document_id": document_id})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Default to 5000 if not set
    app.run(host="0.0.0.0", port=port)
