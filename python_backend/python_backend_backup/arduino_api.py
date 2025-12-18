"""
Arduino Control API - Flask endpoint riêng
Run độc lập: python arduino_api.py
Hoặc import vào app.py chính
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from serial_bridge import home_robot, start_robot, stop_robot

app_arduino = Flask(__name__)
CORS(app_arduino, resources={r"/*": {"origins": "*"}})

@app_arduino.route('/api/arduino/command', methods=['POST'])
def arduino_command():
    """Gửi command trực tiếp đến Arduino qua serial"""
    try:
        data = request.get_json()
        command = data.get('command', '').lower()
        
        if command == 'home':
            success = home_robot()
            return jsonify({
                "status": "success" if success else "error",
                "message": "Robot moving to home" if success else "Failed to send home command",
                "command": "home"
            })
        
        elif command == 'start':
            class_ids = data.get('class_ids', [])
            success = start_robot(class_ids)
            return jsonify({
                "status": "success" if success else "error",
                "message": f"Robot started with {len(class_ids)} classes" if success else "Failed to start",
                "command": "start",
                "class_ids": class_ids
            })
        
        elif command == 'stop':
            success = stop_robot()
            return jsonify({
                "status": "success" if success else "error",
                "message": "Robot stopped" if success else "Failed to stop",
                "command": "stop"
            })
        
        else:
            return jsonify({"error": f"Unknown command: {command}"}), 400
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("🚀 Starting Arduino Control API on http://localhost:5001")
    print("📡 Forward commands to main.py serial on COM4")
    app_arduino.run(host='0.0.0.0', port=5001, debug=True)
