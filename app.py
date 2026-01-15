from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route("/")
def home():
    return "<h1>Bot Running Successfully 🎉</h1><p>Flask Service Active!</p>"

@app.route("/start")
def start():
    return jsonify({"status": "ok", "message": "Bot Started Successfully!"})

@app.route("/features")
def features():
    return jsonify({
        "GM & GN Auto Wishes": True,
        "Owner": "Ankit Shakya",
        "Developer": "Ankit Shakya",
        "AI Footer": "© 2025 Ankit Shakya",
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1000)
