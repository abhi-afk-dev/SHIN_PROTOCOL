import base64
from flask import Flask, request, Response, stream_with_context,jsonify
from flask_cors import CORS
from agents import ShinSwarm

app = Flask(__name__)
CORS(app)

swarm = ShinSwarm()

@app.route('/')
def home():
    return jsonify({"status": "Shin Protocol Online", "system": "Flask"})

@app.route('/investigate', methods=['POST'])
def start_investigation():
    data = request.get_json(silent=True) or {}
    
    claim_text = data.get('claim_text', request.form.get('claim_text', ''))
    image_input = data.get('image_url')
    is_file = False

    if 'file' in request.files:
        is_file = True
        file = request.files['file']
        image_input = base64.b64encode(file.read()).decode('utf-8')

    if not image_input and not claim_text:
        return {"error": "No input"}, 400

    return Response(
        stream_with_context(swarm.investigate_stream_sync(image_input, claim_text, is_file)),
        mimetype='application/x-ndjson'
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)