class EventLoop:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(EventLoop, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        pass
