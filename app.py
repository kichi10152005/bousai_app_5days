from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from urllib.parse import urlparse, urljoin
from functools import wraps
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

# app.py はプロジェクト直下に置く。
# 実体（templates / static / data）は bousai_app/ 配下にあるので、そこを参照する。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, 'bousai_app')

app = Flask(
    __name__,
    template_folder=os.path.join(APP_DIR, 'templates'),
    static_folder=os.path.join(APP_DIR, 'static'),
)
app.secret_key = 'your-secret-key-here'

# 管理者認証情報
ADMIN_CREDENTIALS = {
    'admin': '123'
}

# ────────────────────────────────
# 気象警報・注意報設定
PREFECTURE_CODE = "020000"  # 青森県
AREA_NAME = "青森市"

# 青森市のJMA市区町村コード（青森県青森市）
AREA_CODE = "0220100"
CITY_NAME = "青森市"

WARNING_URL = (
    f"https://www.jma.go.jp/bosai/warning/data/r8/{PREFECTURE_CODE}.json"
)

JST = timezone(timedelta(hours=9))

# 警報・注意報のコード一覧
WARNING_CODES = {
    "00": "解除",
    "02": "暴風雪警報",
    "03": "レベル3大雨警報",
    "04": "洪水警報",
    "05": "暴風警報",
    "06": "大雪警報",
    "07": "波浪警報",
    "08": "レベル3高潮警報",
    "09": "レベル3土砂災害警報",
    "10": "レベル2大雨注意報",
    "12": "大雪注意報",
    "13": "風雪注意報",
    "14": "雷注意報",
    "15": "強風注意報",
    "16": "波浪注意報",
    "17": "融雪注意報",
    "18": "洪水注意報",
    "19": "レベル2高潮注意報",
    "20": "濃霧注意報",
    "21": "乾燥注意報",
    "22": "なだれ注意報",
    "23": "低温注意報",
    "24": "霜注意報",
    "25": "着氷注意報",
    "26": "着雪注意報",
    "27": "その他の注意報",
    "29": "レベル2土砂災害注意報",
    "32": "暴風雪特別警報",
    "33": "レベル5大雨特別警報",
    "35": "暴風特別警報",
    "36": "大雪特別警報",
    "37": "波浪特別警報",
    "38": "レベル5高潮特別警報",
    "39": "レベル5土砂災害特別警報",
    "43": "レベル4大雨危険警報",
    "48": "レベル4高潮危険警報",
    "49": "レベル4土砂災害危険警報"
}

# ────────────────────────────────
# サンプルデータの読み込み
DATA_FILE = os.path.join(APP_DIR, 'data', 'shelters.json')
INSTRUCTIONS_FILE = os.path.join(APP_DIR, 'data', 'instructions.json')

def load_json(path, default):
    """JSONファイルを読み込む（存在しない・壊れている場合は default を返す）"""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

shelters = load_json(DATA_FILE, [])
instructions = load_json(INSTRUCTIONS_FILE, [])

for shelter in shelters:
    if isinstance(shelter, dict):
        shelter.setdefault('city', CITY_NAME)

def save_instructions():
    """指示ボードのデータをファイルに保存する"""
    try:
        with open(INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(instructions, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_shelters():
    """避難所データをファイルに保存する"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(shelters, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def geocode_shelter(shelter_name, address):
    """避難所名または住所から青森市内の座標を取得する"""
    queries = [shelter_name, address]
    for query in queries:
        if not query:
            continue
        params = urllib.parse.urlencode({
            'q': query,
            'format': 'jsonv2',
            'limit': 5,
            'countrycodes': 'jp',
            'bounded': 1,
            'viewbox': '139.8,41.3,141.5,40.3'
        })
        try:
            request = urllib.request.Request(
                f'https://nominatim.openstreetmap.org/search?{params}',
                headers={'User-Agent': 'bousai-app/1.0'}
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                results = json.loads(response.read())
        except Exception:
            continue

        for result in results:
            display_name = result.get('display_name', '')
            if '青森市' not in display_name or '弘前市' in display_name:
                continue
            try:
                latitude = float(result['lat'])
                longitude = float(result['lon'])
            except (KeyError, TypeError, ValueError):
                continue
            if 40.3 <= latitude <= 41.3 and 139.8 <= longitude <= 141.5:
                return latitude, longitude
    return None, None
# ────────────────────────────────

# ────────────────────────────────
# 認証関連の設定とヘルパー関数
def is_safe_url(target):
    """リダイレクト先URLが安全かどうかチェック"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def login_required(f):
    """認証が必要なページに付けるデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            # 現在のURLをnextパラメータとしてログイン画面にリダイレクト
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_japan_time():
    """日本時間（JST）の現在時刻を取得する"""
    return datetime.now(JST).strftime("%Y年%m月%d日 %H:%M")


def format_report_time(iso_str):
    """気象庁の発表時刻（ISO形式）をJSTの表示用文字列に変換する"""
    if not iso_str:
        return "不明"
    try:
        parsed = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        if parsed.tzinfo:
            parsed = parsed.astimezone(JST)
        return parsed.strftime("%Y年%m月%d日 %H:%M")
    except ValueError:
        return iso_str


def filter_shelters(district=None):
    """district 指定があれば一致する避難所のみ、なければ全件を返す"""
    return [
        s for s in shelters
        if s.get('city') == CITY_NAME
        and (not district or s.get('district') == district)
    ]


def _shelter_values(shelter, field):
    """避難所の配列またはカンマ区切り文字列を検索用の集合にする"""
    value = shelter.get(field, [])
    if isinstance(value, str):
        return {item.strip() for item in value.replace('、', ',').split(',') if item.strip()}
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    return set()


def search_shelters(name='', location='', equipment=None, hazards=None, district=''):
    """青森市の避難所を指定条件のAND検索で絞り込む"""
    equipment = set(equipment or [])
    hazards = set(hazards or [])
    equipment_aliases = {
        'バリアフリー': {'バリアフリー', 'バリアフリー設備'},
        'ペット対応': {'ペット対応', 'ペット対応設備'},
    }
    results = []
    for shelter in filter_shelters():
        if name and name not in shelter.get('name', ''):
            continue
        if district and shelter.get('district') != district:
            continue
        if location and shelter.get('location') != location:
            continue
        shelter_equipment = _shelter_values(shelter, 'equipment')
        if any(not (shelter_equipment & equipment_aliases.get(item, {item})) for item in equipment):
            continue
        shelter_hazards = _shelter_values(shelter, 'hazards') or _shelter_values(shelter, 'disaster')
        if not hazards.issubset(shelter_hazards):
            continue
        results.append(shelter)
    return results


def shelter_sort_key(shelter):
    """欠損や不正なスコア・距離でも安定して並べ替える"""
    try:
        score = float(shelter.get('score', 0) or 0)
    except (TypeError, ValueError):
        score = 0
    try:
        distance = float(shelter.get('distance_m', float('inf')) or float('inf'))
    except (TypeError, ValueError):
        distance = float('inf')
    return -score, distance


def warning_severity(code):
    """気象庁コードを画面表示用の重要度に変換する"""
    try:
        numeric_code = int(code)
    except (TypeError, ValueError):
        return '中'
    if 32 <= numeric_code <= 39 or numeric_code in (43, 48, 49):
        return '大'
    if 2 <= numeric_code <= 9:
        return '大'
    return '中'


def parse_area_warnings(warning_data):
    """気象庁の新形式JSONから対象市区町村の発表・継続中の情報を抽出する"""
    if not isinstance(warning_data, list):
        raise ValueError("気象庁の警報・注意報データが新形式の配列ではありません")

    warnings = []
    seen_codes = set()
    report_datetimes = []

    for report in warning_data:
        if not isinstance(report, dict):
            continue

        report_datetime = report.get("reportDatetime")
        if isinstance(report_datetime, str) and report_datetime:
            report_datetimes.append(report_datetime)

        warning = report.get("warning")
        if not isinstance(warning, dict):
            continue

        class20_items = warning.get("class20Items", [])
        if not isinstance(class20_items, list):
            continue

        area = next(
            (
                item for item in class20_items
                if isinstance(item, dict)
                and item.get("areaCode") == AREA_CODE
            ),
            None
        )
        if not area:
            continue

        kinds = area.get("kinds", [])
        if not isinstance(kinds, list):
            continue

        for kind in kinds:
            if not isinstance(kind, dict):
                continue

            status = kind.get("status", "")
            code = kind.get("code", "")
            if status not in ("発表", "継続") or not code or code in seen_codes:
                continue

            warnings.append({
                "name": WARNING_CODES.get(
                    code,
                    f"不明な警報・注意報 (コード: {code})"
                ),
                "code": code,
                "status": status,
                "area_name": area.get("areaName", CITY_NAME),
                "area_code": area.get("areaCode", AREA_CODE),
                "severity": warning_severity(code)
            })
            seen_codes.add(code)

    latest_report_datetime = max(report_datetimes, default="")
    return warnings, latest_report_datetime


def get_weather_warnings():
    """対象市区町村の警報・注意報を取得する"""
    try:
        # 青森県の新形式（令和8年～）警報・注意報データを取得
        with urllib.request.urlopen(url=WARNING_URL, timeout=10) as res:
            warning_data = json.loads(res.read())

        warnings, report_datetime = parse_area_warnings(warning_data)

        return {
            "area_name": AREA_NAME,
            "warnings": warnings,
            "report_time": format_report_time(report_datetime),
            "last_fetch_time": get_japan_time()
        }

    except Exception:
        return {
            "area_name": AREA_NAME,
            "warnings": [],
            "report_time": "取得失敗",
            "last_fetch_time": get_japan_time(),
            "error": True
        }


# トップページ：templates/index.html を返す（住民向け指示も表示する）
@app.route('/')
def index():
    resident_notices = [i for i in instructions if i.get('target') == '住民']
    return render_template(
        'index.html',
        resident_notices=resident_notices,
        shelters=filter_shelters()
    )

# ログインページ
@app.route('/login', methods=['GET', 'POST'])
def login():
    # リダイレクト先を取得（デフォルトは避難所登録画面）
    next_url = request.args.get('next') or request.form.get('next')

    # 安全でないURLの場合はデフォルトページにリダイレクト
    if not next_url or not is_safe_url(next_url):
        next_url = url_for('shelter_register')

    if request.method == 'POST':
        password = request.form.get('password', '').strip()

        # 認証チェック
        username = next(
            (name for name, registered_password in ADMIN_CREDENTIALS.items()
             if registered_password == password),
            None
        )
        if username:
            session['logged_in'] = True
            session['username'] = username
            # ログイン成功後は指定されたページにリダイレクト
            return redirect(next_url)
        return render_template('login.html', error=True, message="パスワードが正しくありません。", next=next_url)

    # ログイン済みの場合は指定されたページにリダイレクト
    if session.get('logged_in'):
        return redirect(next_url)

    return render_template('login.html', next=next_url)

# ログアウト
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# 避難所登録ページ
@app.route('/shelter_register', methods=['GET', 'POST'])
@login_required
def shelter_register():
    if request.method == 'POST':
        shelter_name = request.form.get('name', '').strip()
        shelter_address = request.form.get('address', '').strip()
        shelter_capacity = request.form.get('capacity', '').strip()
        selected_equipment = request.form.getlist('equipment')
        other_equipment = request.form.get('equipment_other', '').strip()
        if other_equipment:
            selected_equipment.append(other_equipment)
        shelter_equipment = ', '.join(selected_equipment)

        selected_disasters = request.form.getlist('disaster')
        other_disaster = request.form.get('disaster_other', '').strip()
        if other_disaster:
            selected_disasters.append(other_disaster)
        shelter_disaster = ', '.join(selected_disasters)
        shelter_image = request.form.get('image', '').strip()

        uploaded_file = request.files.get('upload_image')
        if uploaded_file and uploaded_file.filename:
            upload_dir = os.path.join(APP_DIR, 'static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            safe_name = uploaded_file.filename
            file_path = os.path.join(upload_dir, safe_name)
            uploaded_file.save(file_path)
            shelter_image = f"/static/uploads/{safe_name}"

        required_fields = {
            '避難所名': shelter_name,
            '避難所住所': shelter_address,
            '避難所許容人数': shelter_capacity,
            '避難所設備詳細': shelter_equipment,
            '対応災害': shelter_disaster,
        }

        missing_field = next((label for label, value in required_fields.items() if not value), None)
        if missing_field:
            return render_template(
                'shelter_register.html',
                error=True,
                message=f'{missing_field}を入力してください。'
            )

        latitude, longitude = geocode_shelter(shelter_name, shelter_address)
        shelter_id = max((s.get('id', 0) for s in shelters), default=0) + 1
        shelters.append({
            'id': shelter_id,
            'name': shelter_name,
            'city': CITY_NAME,
            'address': shelter_address,
            'latitude': latitude,
            'longitude': longitude,
            'capacity': shelter_capacity,
            'equipment': shelter_equipment,
            'disaster': shelter_disaster,
            'image': shelter_image,
        })
        save_shelters()

        return render_template(
            'shelter_register.html',
            success=True,
            message='避難所名を登録しました。'
        )

    return render_template('shelter_register.html')

# 避難所検索ページ
@app.route('/shelter_search')
def shelter_search():
    search_conditions = {
        'name': request.args.get('name', '').strip(),
        'location': request.args.get('location', '').strip(),
        'equipment': request.args.getlist('equipment'),
        'hazard': request.args.getlist('hazard'),
    }
    results = search_shelters(
        search_conditions['name'],
        search_conditions['location'],
        search_conditions['equipment'],
        search_conditions['hazard']
    ) if request.args else None
    return render_template(
        'shelter_search.html',
        conditions=search_conditions,
        results=results,
        shelters=filter_shelters()
    )

# 全施設一覧ページ
@app.route('/all_shelters')
def all_shelters():
    return render_template('search_results.html', results=filter_shelters())


# 指示ボード：住民向けの指示を一覧で確認する
@app.route('/board')
@login_required
def board():
    resident_instructions = [i for i in instructions if i.get('target') == '住民']
    return render_template('board.html', instructions=resident_instructions)

# 検索結果ページ：templates/search_results.html を返す
@app.route('/search_results')
def search_results():
    conditions = {
        'name': request.args.get('name', '').strip(),
        'location': request.args.get('location', '').strip(),
        'equipment': request.args.getlist('equipment'),
        'hazard': request.args.getlist('hazard'),
        'district': request.args.get('district', '').strip(),
    }
    results = search_shelters(
        conditions['name'], conditions['location'],
        conditions['equipment'], conditions['hazard'], conditions['district']
    )
    results.sort(key=shelter_sort_key)
    return render_template('search_results.html', results=results, conditions=conditions)

# JSON API：/shelters?district=地区名
@app.route('/shelters', methods=['GET'])
def get_shelters():
    results = filter_shelters(request.args.get('district'))

    if not results:
        # 見つからなければエラー JSON を返す
        return jsonify({'error': 'No shelters found'}), 404

    # 見つかったらリストを JSON で返す
    return jsonify(results)

# 気象警報・注意報API
@app.route('/api/weather_warnings')
def api_weather_warnings():
    """気象警報・注意報をJSON形式で返すAPI"""
    return jsonify(get_weather_warnings())

if __name__ == '__main__':
    app.run(debug=True, port=5000)
