from app_instance import app
import threading

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5555, debug=True, use_reloader=False)
