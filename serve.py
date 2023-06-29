import os
import json
import tornado.ioloop
import tornado.web
import tornado.websocket

import glob
from PIL import Image, ExifTags, TiffImagePlugin


def all_images():
    images = []
    for ext in ("jpg", "png", "gif"):
        images.extend(glob.glob(f"*.{ext}"))
    return images


def get_exif(path):
    img = Image.open(path)
    exif = img.getexif()

    data = {}
    for k, v in exif.items():
        if k in ExifTags.TAGS:
            tag = ExifTags.TAGS[k]
            if isinstance(v, TiffImagePlugin.IFDRational):
                v = float(v)
            data[tag] = v

    return data


def set_exif_comment(path, data):
    img = Image.open(path)
    exif = img.getexif()
    exif[0x9286] = data
    img.save(path, exif=exif)


class DB:
    def __init__(self):
        self.path = "./db.json"
        self.db = {}
        self.callbacks = []

        if os.path.exists(self.path):
            self.db = json.load(open(self.path, "r"))

        self.db["images"] = {
            path: get_exif(path)
            for path in all_images()
        }

    def op(self, op, path, data):
        location = self.db
        for i in range(len(path) - 1):
            location = location[path[i]]

        if op == "SUBSCRIBE":
            self.callbacks.append(data)
        elif op == "PUT":
            location[path[-1]] = data
        elif op == "DELETE":
            del location[path[-1]]

        self.side_effects(op, path, data)

        for cb in self.callbacks:
            cb(self.db)

        json.dump(self.db, open("./db.json", "w"), indent=2)

    def side_effects(self, op, path, data):
        # When an EXIF comment changes, persist!
        if path and path[-1] == "UserComment":
            set_exif_comment(path[1], data)
            print("set exif comment", path[1], data)


db = DB()


class WSHandler(tornado.websocket.WebSocketHandler):
    def on_message(self, msg):
        msg = json.loads(msg)

        if msg["op"] == "SUBSCRIBE":
            def cb(db):
                if self.ws_connection:
                    self.write_message(json.dumps(db))
            msg["data"] = cb

        db.op(msg["op"], msg["path"], msg["data"])


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("interface.html")


if __name__ == "__main__":
    app = tornado.web.Application([
        (r'/', IndexHandler),
        (r'/ws', WSHandler),
        (r'/static/(.*)', tornado.web.StaticFileHandler, {"path": "."}),
    ], debug=True)

    app.listen(1234)
    tornado.ioloop.IOLoop.current().start()
