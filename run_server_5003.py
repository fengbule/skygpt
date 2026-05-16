import sys
import os

sys.path.insert(0, r"c:\Cline\skygpt_upload")

from web.app import app, socketio

port = int(os.environ.get("SKYGPT_PORT", "5003"))

socketio.run(app, host="127.0.0.1", port=port, debug=False, allow_unsafe_werkzeug=True)