from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug=False on purpose: the Flask reloader would start the collector thread twice.
    app.run(host="0.0.0.0", port=5000, debug=False)
