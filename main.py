from utime import ticks_ms, ticks_diff, sleep, sleep_ms
from machine import Pin
from hx711_gpio import *
from wificonnect import *
import uasyncio
import picoweb
import ure as re
import json

# global variables
MIN_WEIGHT = 10
MAX_WEIGHT = 9999.99

ledred = Pin(27, Pin.OUT)
ledgreen = Pin(26, Pin.OUT)
ledblue = Pin(25, Pin.OUT)

weight_rear = 0
weight_front = 0
weight = weight_rear + weight_front
cg = 0

def set_rgb(r=0, g=0, b=0):
    ledred.value(not r)
    ledgreen.value(not g)
    ledblue.value(not b)
    
def connection(ssid='', password='', name=''):
    ip = ''
    ap = True
    try:
        ip = connectSTA(ssid, password,name)
        ap = False
    except:
        ip = ''
        try:
            ip = connectAP(name) 
        except:
            ip = ''
    return ip, ap


def hx_init(pin_out,pin_sck):        # create object load_cell; pin_out,pin_sck = int
    out = Pin(pin_out, Pin.IN, pull=Pin.PULL_DOWN)
    sck = Pin(pin_sck, Pin.OUT)
    hx = HX711(sck, out)
    hx.OFFSET = 0
    hx.set_gain(128)
    hx.set_time_constant(0.50)
    return hx


def tare(hx, times=15):
    hx.tare(times)
    
def write_config(config):
    f = open('config.json','w')
    json.dump(config, f)
    f.close()

def read_config():
    f = open('config.json','r')
    config = json.load(f)
    f.close()
    return config

def split_config(config):
    global lcfrontcal, lcrearcal, supportsdist, supportledist, supportledist, lang
    # config = {"lcfrontcal": 1004.65, "lcrearcal": 663.27, "supportsdist": 230, "lang": 1, "supportledist": 28}
    lcfrontcal = config["lcfrontcal"]
    lcrearcal = config["lcrearcal"]
    supportsdist = config["supportsdist"]
    supportledist = config["supportledist"]
    lang = config["lang"]
    print('lcrearcal =', lcrearcal)
    print('lcfrontcal =', lcfrontcal)
    print('supportsdist =', supportsdist)
    print('supportledist =', supportledist)
    print('lang =', lang)
    

def update_weight(hx):
    global MIN_WEIGHT, MAX_WEIGHT
    weight = round(hx.get_units(),2)
    if weight < MIN_WEIGHT:
        weight = 0.00
    elif weight > MAX_WEIGHT:
        weight = MAX_WEIGHT
    return weight

def calc_cg(rear, front):
    global supportsdist, supportledist
    global config
    if (rear == 0) or (front == 0):
        cg = -1
        return cg
    supportledist = config["supportsdist"]
    supportledist = config["supportledist"]
    compute = (config["supportsdist"] * rear) / (rear + front)
    # basic check to remove absurd situations:
    # Over the supports_dist ... the plane should fall from the scale */
    if (compute > supportsdist + supportledist):
        cg = -1.0
        return cg
    else:
      cg = round(compute + supportledist,1)
    return cg

def calibrate(hx):
    global config
    raw_weight = hx.read_average(times=100)
    divider = (raw_weight - hx.OFFSET) / config['calweight']
    hx.set_scale(divider) 
    return divider
    
# ---- Routing Picoweb ------------------------------------ 
app = picoweb.WebApp(__name__)
@app.route("/xhr")
def index(req, resp):
    global weight_rear, weight, weight_front, cg, lang
    global lcfrontcal, lcrearcal
    global lc_rear, lc_front
    global config
    req.parse_qs()
    request = req.form
    if (req.form.get('getconfig') == '1') and (len(req.form) ==1):
        config = read_config()
        json = config
    elif req.form.get('getlive') == '1':
        if req.form.get('config') == '1':
            weight_rear = update_weight(lc_rear)
            weight_front = update_weight(lc_front)
            json = {"err": False,
                    "cfg_weight_rear": f"{weight_rear:07.2f}",
                    "cfg_weight_front": f"{weight_front:07.2f}",
                    "lcfrontcal": lcfrontcal,
                    "lcrearcal": lcrearcal}
        else:
            weight_rear = update_weight(lc_rear)
            weight_front = update_weight(lc_front)
            weight = weight_rear+weight_front
            cg = calc_cg(weight_rear, weight_front)
            json = {"err": False,
                    "weight_rear": f"{weight_rear:07.2f}",
                    "weight_front": f"{weight_front:07.2f}",
                    "weight": f"{weight:07.2f}",
                    "cg": f"{cg:05.1f}"}
    elif req.form.get('tare') == '1':
        tare(lc_rear)
        tare(lc_front)
        json = {"err": False}
    elif req.form.get('calibrate') == '1':
        if req.form.get('calfront') == '1':
            lcfrontcal = calibrate(lc_front)
            config["lcfrontcal"] = lcfrontcal
            json = {"err": False}
        elif req.form.get('calrear') == '1':
            lcrearcal = calibrate(lc_rear)
            config["lcrearcal"] = lcrearcal
            json = {"err": False}
        else:
            json = {"err": True}
    elif req.form.get('setconfig') == '1':
        mod = 0
        if req.form.get('lcrearcal','false') != 'false':
            lcrearcal = float(req.form.get('lcrearcal'))
            config["lcrearcal"] = lcrearcal
            lc_rear.set_scale(lcrearcal)
            mod = 2
            json = {"err": False,
                    "updated": mod}
        elif req.form.get('lcfrontcal','false') != 'false':
            lcfrontcal = float(req.form.get('lcfrontcal'))
            config["lcfrontcal"] = lcfrontcal
            lc_front.set_scale(lcfrontcal)
            mod = 2
            json = {"err": False,
                    "updated": mod}
        elif req.form.get('calweight','false') != 'false':
            calweight = float(req.form.get('calweight'))
            config["calweight"] = calweight
            mod = 2
            json = {"err": False,
                    "updated": mod}
        elif req.form.get('lang','false') != 'false':
            lang = int(req.form.get('lang'))
            config["lang"] = lang
            mod = 1
            json = {"err": False,
                    "updated": mod}
        elif req.form.get('supportsdist','false') != 'false':
            supportsdist = int(req.form.get('supportsdist'))
            config["supportsdist"] = supportsdist
            lc_front.set_scale(supportsdist)
            print("SET supportsdist", supportsdist)
            json = {"err": False,
                    "updated": mod}
        elif req.form.get('supportledist','false') != 'false':
            supportledist = int(req.form.get('supportledist'))
            config["supportledist"] = supportledist
            lc_front.set_scale(supportledist)
            mod = 1
            json = {"err": False,
                    "updated": mod}
        elif req.form.get('save','false') != 'false':
            write_config(config)
            mod = 1
            json = {"err": False,
                    "updated": mod}
    yield from picoweb.jsonify(resp,json)


@app.route("/")
def index(req, resp):
    yield from picoweb.start_response(resp)
    yield from app.sendfile(resp, '/www/index.html')
    set_rgb(0,1,0)


@app.route("/style.css")
def index(req, resp):
    print("Send style.css")
    yield from picoweb.start_response(resp)
    yield from app.sendfile(resp, '/www/style.css')


@app.route("/background_main.jpg")
def index(req, resp):
    print("Send JPG")
    yield from picoweb.start_response(resp)
    try:
        with open("www/background_main.jpg", 'rb') as img_binary:
            img= img_binary.read()
        yield from resp.awrite(img)
    except Exception:
        print("Image file not found.")
        pass
    
# --------------- main --------------------
import ulogging as logging
logging.basicConfig(level=logging.INFO)

set_rgb(1,0,0)
# rear load_cell
lc_rear = hx_init(23, 22)
# front  load_cell
lc_front = hx_init(21, 19)
config = read_config()
split_config(config)
lc_rear.set_scale(lcrearcal)
lc_front.set_scale(lcfrontcal)
ipaddress, ap = connection(ssid='<Your_SSID>', password='<Your_Password>', name='CGScale')
if ipaddress:
    if ap:
        set_rgb(1,0,1)
    else:
        set_rgb(0,0,1)
    app.run(debug=False, host = ipaddress, port = 80)
    print("Waitiing for httpRequest...")
else:
    print("No connection....")
