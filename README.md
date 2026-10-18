# Chrome Profile Manager (Profile YTB)

Ứng dụng desktop cho **Ubuntu** để quản lý nhiều Chrome profile và **tự động hóa** công việc trên chúng:
mở/đóng hàng loạt, chạy tác vụ theo lịch, **tự public video nháp trên YouTube Studio** (không cần
cài extension), điều khiển từ
dòng lệnh (cron, script) và từ Playwright/Selenium.

> Không chạy ứng dụng bằng `sudo`. Hãy chạy bằng đúng user Linux đang sở hữu Chrome profile.

---

## Mục lục

1. [Cài đặt nhanh](#1-cài-đặt-nhanh)
2. [Sử dụng giao diện](#2-sử-dụng-giao-diện)
3. [Tự động hóa](#3-tự-động-hóa)
   - [3.1 Profile riêng và Chrome gốc](#31-profile-riêng-và-chrome-gốc--đọc-trước)
   - [3.2 Cấu hình tự động cho từng profile](#32-cấu-hình-tự-động-cho-từng-profile)
   - [3.3 Tác vụ và lịch chạy](#33-tác-vụ-và-lịch-chạy)
   - [3.4 Tự public YouTube](#34-tự-public-youtube)
   - [3.5 Điều khiển bằng dòng lệnh (cpm)](#35-điều-khiển-bằng-dòng-lệnh-cpm)
   - [3.6 Playwright và Selenium qua CDP](#36-playwright-và-selenium-qua-cdp)
   - [3.7 Chạy nền 24/7](#37-chạy-nền-247)
   - [3.8 Điều khiển bằng Hermes Agent](#38-điều-khiển-bằng-hermes-agent)
4. [Chạy trên máy Ubuntu khác và build](#4-chạy-trên-máy-ubuntu-khác-và-build)
5. [Dữ liệu ứng dụng và sao lưu](#5-dữ-liệu-ứng-dụng-và-sao-lưu)
6. [Lỗi thường gặp](#6-lỗi-thường-gặp)
7. [Dành cho người phát triển](#7-dành-cho-người-phát-triển)

---

## 1. Cài đặt nhanh

Yêu cầu: Ubuntu 22.04 trở lên, Python 3.10 trở lên, đã cài Google Chrome hoặc Chromium.

```bash
cd "/đường/dẫn/Profile YTB"
./scripts/install_ubuntu.sh      # tạo .venv và cài thư viện
./scripts/run.sh                 # mở ứng dụng
```

Nếu Ubuntu báo thiếu thư viện giao diện Qt:

```bash
sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libxcb-xinerama0
```

---

## 2. Sử dụng giao diện

### Trang Chrome Profiles

| Khu vực | Chức năng |
|---|---|
| **+ Thêm profile** | Tạo profile riêng. Đường dẫn Chrome được tự điền. |
| **Công cụ ▾** | Quét profile Chrome có sẵn trên máy, nhập/xuất cấu hình JSON, đóng tất cả. |
| Ô tìm kiếm | Tìm theo tên, nhóm, mục đích, tag, ghi chú. |
| Bộ lọc | Trạng thái (Đã ghim, Quan trọng, Đang chạy…) và **Nhóm**. |
| Thanh nút | **Mở / Đóng / Sửa / Quan trọng / Xóa** áp dụng cho các dòng đang chọn. |
| Bảng | Màu, tên (📌 ghim, ★ quan trọng), trạng thái có màu, nhóm, mục đích, tags, nguồn, thư mục, **cổng CDP**. |
| Chuột phải | Khởi động lại, nhân bản cấu hình, mở thư mục dữ liệu… |

**Phím tắt**

| Phím | Tác dụng |
|---|---|
| `Enter` / nhấp đúp | Mở profile đang chọn |
| `F2` | Sửa profile |
| `Delete` | Xóa vĩnh viễn (có hỏi xác nhận) |
| `Ctrl+N` | Thêm profile |
| `Ctrl+F` | Tìm kiếm |
| `Ctrl+A` | Chọn tất cả (khi đang ở bảng) |
| `F5` | Làm mới |

Chọn nhiều dòng bằng `Ctrl` + click hoặc `Shift` + click.

### Xóa profile

Bấm **Xóa** (hoặc phím `Delete`) và xác nhận để **xóa vĩnh viễn**, không khôi phục được:

- Toàn bộ thư mục dữ liệu của profile (đăng nhập, cookie, lịch sử, extension, cache).
- Với profile Chrome gốc: thư mục `Profile N` trong thư mục Chrome (`~/.config/google-chrome` trên
  Ubuntu, `%LOCALAPPDATA%\Google\Chrome\User Data` trên Windows) và mục của nó trong file
  `Local State`, nên profile cũng biến mất khỏi Chrome. Phải **đóng hết Google Chrome** trước.
- Tác vụ chỉ chạy cho profile đó và lịch sử chạy của nó. Tác vụ theo nhóm được giữ cho các profile
  còn lại trong nhóm.

Profile còn nằm trong thùng rác từ phiên bản cũ được xóa hẳn ở lần mở app tiếp theo.

### Form thêm/sửa profile

Form có 3 tab:

- **Cơ bản**: tên, nhóm (chọn từ danh sách để không gõ sai), mục đích, tags, màu, ghim, ghi chú.
- **Tự động hóa**: link Studio của kênh, cấu hình JSON mặc định, bật cổng CDP. Xem [mục 3.2](#32-cấu-hình-tự-động-cho-từng-profile).
- **Nâng cao**: đường dẫn Chrome, startup URL, tham số dòng lệnh, proxy (http, https, socks4, socks5).

---

## 3. Tự động hóa

### 3.1 Profile riêng và Chrome gốc (đọc trước)

| | **Profile riêng** (tạo bằng “+ Thêm profile”) | **Chrome gốc** (từ “Quét profile Chrome”) |
|---|---|---|
| Thư mục dữ liệu | Mỗi profile một thư mục riêng | Dùng chung `~/.config/google-chrome` |
| Chạy song song | ✅ Mỗi profile một tiến trình Chrome | ❌ Chung một tiến trình Chrome |
| Đóng một profile | Chỉ đóng profile đó | Có thể đóng **toàn bộ** Chrome |
| Cổng CDP | ✅ | ❌ Chrome 136+ chặn CDP trên thư mục mặc định |
| Public YouTube tự động | ✅ | ❌ |

👉 **Để chạy tự động nhiều kênh, hãy dùng Profile riêng.**

**Đã có kênh đăng nhập sẵn trong Chrome gốc?** Đóng Google Chrome, chuột phải profile đó →
**⇪ Chuyển thành Profile riêng (giữ đăng nhập)**.
- App chép dữ liệu (cookie, đăng nhập, extension) sang một Profile riêng mới và **giữ nguyên profile
  gốc**. Cache được bỏ qua để chép nhanh.
- Mở profile mới để kiểm tra. Nếu Google yêu cầu đăng nhập lại thì đăng nhập một lần là xong. Đăng nhập YouTube một lần trong mỗi
profile riêng; lần sau mở lại vẫn còn đăng nhập.

### 3.2 Cấu hình tự động cho từng profile

Mở **Sửa profile → tab Tự động hóa**:

- **Link Studio của kênh**, ví dụ `https://studio.youtube.com/channel/UCxxxx/videos`. Tác vụ
  *Public YouTube* sẽ mở đúng trang này. Để trống thì mở trang Studio mặc định.
- **Thư mục thumbnail**: thư mục chứa ảnh thumbnail của kênh, có thể có thư mục con. Tên file phải
  **bắt đầu bằng số thứ tự của video nháp**, theo sau là `_`, dấu cách hoặc `-`. Ví dụ
  `12_ten video.jpg` hoặc `12 - abc.png` ứng với nháp `12 Tên video`. Chỉ nhận JPG/PNG, tối đa 2 MB.
  Nếu hai file cùng số, cả hai bị bỏ qua và ghi vào lịch sử. Để trống thì dùng thumbnail đã nhập
  trước đó bằng popup của extension cũ (nếu có).
- **Cấu hình khác (JSON)**: các thiết lập cho quy trình public. Ví dụ:

  ```json
  {
    "visibility": "public",
    "maxVideos": 5,
    "delayMin": 1500,
    "delayMax": 3000,
    "randomDelay": true,
    "monetizationChannel": false,
    "skipMissing": true
  }
  ```

  | Khóa | Ý nghĩa |
  |---|---|
  | `visibility` | `public`, `unlisted` hoặc `private` |
  | `maxVideos` | Số nháp xử lý mỗi lần, `0` là tất cả |
  | `delayMin` / `delayMax` | Thời gian nghỉ giữa các bước (mili giây) |
  | `skipMissing` | `true`: bỏ qua nháp không có thumbnail; `false`: vẫn public mà không có thumbnail |
  | `monetizationChannel` | `true`: tự bật kiếm tiền ở bước Monetization |
  | `scheduleMode`, `scheduleDate` (`2026-10-20`), `scheduleTime` (`08:00`), `videosPerDay` | Lên lịch thay vì public ngay |
  | `timeout` | Thời gian tối đa của một lần chạy (giây), mặc định 4 giờ |

  Thứ tự áp dụng (cái sau ghi đè cái trước):
  1. Mặc định của app: `scheduleMode: false`, `skipMissing: true`
  2. JSON của profile
  3. Thiết lập trong tác vụ

- **Bật cổng điều khiển CDP**: lần mở đầu tiên app tự gán một cổng (từ 9222 trở lên). Cổng giữ cố
  định cho profile và hiện ở cột **CDP** của bảng. Tác vụ *Public YouTube* **tự bật** mục này. Xem
  [mục 3.6](#36-playwright-và-selenium-qua-cdp).

### 3.3 Tác vụ và lịch chạy

Vào mục **Tác vụ → + Tạo tác vụ**.

**Chạy cho**

- **Một profile**, hoặc
- **Cả nhóm**: chạy **lần lượt** từng profile trong nhóm (sắp theo tên). Có thể đặt **thời gian
  nghỉ giữa các profile** (giây) để tránh mở quá nhiều Chrome cùng lúc hoặc bị YouTube nghi ngờ.
  Profile mới thêm vào nhóm sẽ tự được tính ở lần chạy sau.

**Hành động**

| Hành động | Mô tả |
|---|---|
| Mở profile / Đóng profile / Khởi động lại | Điều khiển cửa sổ Chrome |
| Mở URL | Mở profile với một URL |
| Mở rồi tự đóng sau N phút | Ví dụ mở 30 phút rồi tự đóng |
| Public YouTube | Tự xử lý các video nháp trong Studio ([mục 3.4](#34-tự-public-youtube)). Chọn **Số video** và **Chế độ hiển thị**, hoặc để “Theo profile”. |

**Lịch**

| Lịch | Ý nghĩa |
|---|---|
| Chạy thủ công | Chỉ chạy khi bấm **▶ Chạy ngay** (hoặc `cpm run-task`) |
| Lặp mỗi N phút | Ví dụ mỗi 60 phút |
| Hằng ngày lúc | Ví dụ 08:00 mỗi ngày |
| Một lần lúc | Một ngày giờ cụ thể trong tương lai |

**Thử lại khi lỗi** (0–5 lần): mỗi lần thử lại cách nhau 30 giây.

**Trang Tác vụ**

- **▶ Chạy ngay**: chạy trong nền, giao diện **không bị treo** dù tác vụ kéo dài hàng giờ.
- **✎ Sửa** (hoặc nhấp đúp), **⏯ Bật/Tắt lịch**, **■ Dừng** (public YouTube dừng sau video đang
  làm), **🗑 Xóa**. Khi xóa, lịch chạy được gỡ ngay.
- Bảng hiển thị **Lần chạy kế** và **Lần chạy cuối**. Rê chuột vào cột trạng thái để xem lỗi.
- Ô **Lịch sử chạy** liệt kê 50 lần chạy gần nhất: thời gian, profile, ✔/✖, số lần thử, lỗi hoặc
  kết quả (ví dụ `Xong 5/6 video, bỏ qua 1; Thiếu thumbnail cho #14`).

> Nếu máy tắt hoặc ngủ đúng giờ chạy, khi app hoạt động lại trong vòng 10 phút, tác vụ vẫn được
> chạy bù **một lần**. Quá 10 phút thì bỏ qua lần đó.

### 3.4 Tự public YouTube

App tự điều khiển YouTube Studio, **không cần cài extension**. Quy trình xử lý từng video nháp giống
hệt extension “bom nguyen tu”: điền tiêu đề, thumbnail, kiếm tiền, đánh giá nội dung, màn hình kết
thúc, chế độ hiển thị hoặc lên lịch, rồi xuất bản.

**Chuẩn bị một lần cho mỗi kênh**

1. Tạo **Profile riêng** cho kênh (Profile Chrome gốc không dùng được).
2. Mở profile và **đăng nhập YouTube**.
3. Sửa profile → tab **Tự động hóa**:
   - **Link Studio**: `https://studio.youtube.com/channel/UCxxxx/videos/upload`. Mở Studio, vào mục
     *Nội dung*, rồi chép link trên thanh địa chỉ.
   - **Thư mục thumbnail** và **JSON** nếu cần (xem [mục 3.2](#32-cấu-hình-tự-động-cho-từng-profile)).

**Chuẩn bị mỗi lần đăng**

- Upload video lên Studio ở dạng **nháp**, tiêu đề **bắt đầu bằng số thứ tự**, ví dụ `12 Tên video`.
  Hai nháp trùng số sẽ làm cả lượt chạy dừng.
- Đặt thumbnail `12_...jpg` vào thư mục thumbnail.

**Chạy:** tạo tác vụ **Public YouTube** cho một profile hoặc cả nhóm, chạy ngay hoặc theo lịch.
Hoặc chạy từ dòng lệnh: `./scripts/cpm.sh run-task "Tên tác vụ"`.

**Cách hoạt động**

1. App mở profile với cổng CDP (tự bật nếu chưa), mở một tab mới tới Link Studio và đưa tab đó lên
   trước.
2. App nạp mã quy trình (`app/studio_js/`, chép từ extension) vào một vùng chạy riêng của tab, giống
   cách extension chạy content script. Mã này không đụng tới mã của trang YouTube.
3. Thumbnail của các nháp sắp xử lý được đọc từ thư mục và nạp vào trình duyệt.
4. App theo dõi tiến độ mỗi 2 giây cho tới khi xong, rồi ghi kết quả vào **Lịch sử chạy**.
   - **Thành công**: tab tự đóng.
   - **Có video lỗi**: tác vụ báo lỗi kèm số thứ tự và lý do, tab được giữ lại để bạn xem.
   - **Lỗi chung** (chưa đăng nhập, không thấy danh sách video…): app chụp màn hình vào
     `logs/screenshots/`.

**Giới hạn**

- Chỉ xử lý các nháp **đang hiện trên trang danh sách đầu tiên** của Studio.
- Khi YouTube đổi giao diện Studio, cần sửa selector trong `app/studio_js/selector-engine.js`.

### 3.5 Điều khiển bằng dòng lệnh (`cpm`)

Dùng cho cron, bash script, n8n… Mọi lệnh **in ra JSON**. Mã thoát `0` là thành công, `1` là có
lỗi.

- **Khi app đang chạy:** lệnh được gửi cho app thực hiện. Chrome mở trên màn hình của bạn, việc dài
  chạy nền, không bao giờ chạy trùng.
- **Khi app không chạy:** lệnh tự thực hiện và chờ đến khi xong.

```bash
./scripts/cpm.sh list                              # liệt kê profile
./scripts/cpm.sh list --group "Team A"
./scripts/cpm.sh open "Kênh A" "Kênh B"            # mở theo tên hoặc ID
./scripts/cpm.sh open --group "Team A"             # mở cả nhóm
./scripts/cpm.sh close --all
./scripts/cpm.sh check "Kênh A"                    # kiểm tra: số nháp, thiếu thumbnail (không đăng)
./scripts/cpm.sh publish "Kênh A" --max 3 --visibility private   # public ngay, không cần tạo tác vụ
./scripts/cpm.sh publish --group "Team A" --wait   # cả nhóm, chờ tới khi xong
./scripts/cpm.sh tasks                             # liệt kê tác vụ
./scripts/cpm.sh run-task "Public sáng" --wait
./scripts/cpm.sh status <task>                     # tiến độ: video thứ mấy, thành công, lỗi
./scripts/cpm.sh stop <task>                       # dừng sau video đang làm
./scripts/cpm.sh history <task>                    # lịch sử chạy
./scripts/cpm.sh cdp "Kênh A"                      # địa chỉ CDP cho Playwright/Selenium
```

`<task>` là ID hoặc tên tác vụ. `publish` và `run-task` trả về `task_id` ngay. Thêm `--wait` để chờ
xong; trong lúc chờ, tiến độ được in ra stderr.

**Ví dụ cron** (app đang chạy dưới khay, nên không cần `DISPLAY`):

```cron
0 8 * * * "/đường/dẫn/Profile YTB/scripts/cpm.sh" publish --group "Team A" --wait >> /tmp/cpm.log 2>&1
```

> Cách đơn giản hơn cron: tạo tác vụ có lịch ngay trong app và bật [chạy nền 24/7](#37-chạy-nền-247).

### 3.6 Playwright và Selenium qua CDP

1. Sửa profile → tab **Tự động hóa** → tích **Bật cổng điều khiển CDP**. Chỉ dùng được với Profile
   riêng.
2. Mở profile (bằng app hoặc `cpm open`). Cột **CDP** sẽ hiện số cổng, ví dụ `9222`.
3. Kết nối từ script. Script dùng chính phiên đăng nhập của profile:

**Playwright (Python)**

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]  # context đã đăng nhập sẵn
    page = context.new_page()
    page.goto("https://studio.youtube.com")
    print(page.title())
```

**Selenium (Python)**

```python
from selenium import webdriver

options = webdriver.ChromeOptions()
options.debugger_address = "127.0.0.1:9222"
driver = webdriver.Chrome(options=options)
driver.get("https://studio.youtube.com")
```

**Lấy cổng theo tên profile trong script**

```bash
./scripts/cpm.sh list | python3 -c \
  'import json,sys; print([p["debug_port"] for p in json.load(sys.stdin) if p["name"]=="Kênh A"][0])'
```

> ⚠️ **Bảo mật**: cổng CDP chỉ nghe trên `127.0.0.1`. Tuy vậy, **mọi chương trình trên máy** đều
> có thể điều khiển profile qua cổng này khi profile đang mở. Chỉ bật CDP cho profile cần chạy
> script.

### 3.7 Chạy nền 24/7

Tác vụ theo lịch **chỉ chạy khi app đang mở**, kể cả khi ẩn dưới khay hệ thống.

1. **Bật khay hệ thống trên GNOME**: Ubuntu đã có sẵn extension *Ubuntu AppIndicators*. Kiểm tra:

   ```bash
   gnome-extensions list --enabled | grep -i appindicator
   ```

   Nếu không có kết quả: `sudo apt install gnome-shell-extension-appindicator`, sau đó đăng xuất
   và đăng nhập lại.

2. **Tự khởi động khi đăng nhập** (app ẩn dưới khay):

   ```bash
   ./scripts/install_autostart.sh            # bật
   ./scripts/install_autostart.sh --remove   # tắt
   ```

   Nếu đã cài bản build vào `~/.local/share/chrome-profile-manager/dist`, script dùng bản build.
   Nếu không, script dùng `scripts/run.sh`.

3. Khi bấm ✕ ở cửa sổ, app thu xuống khay. Muốn thoát hẳn, bấm chuột phải biểu tượng trên khay →
   **Thoát hoàn toàn**. Nếu máy không có khay, bấm ✕ sẽ thoát hẳn để tránh app chạy ẩn mà không
   mở lại được.

4. Nên tắt chế độ ngủ của máy (*Settings → Power*) nếu cần chạy theo lịch vào ban đêm.

---

### 3.8 Điều khiển bằng Hermes Agent

Hermes Agent (Nous Research) chạy trên **VPS** hoặc một máy khác, và điều khiển Profile YTB trên máy
Windows/Ubuntu của bạn. Bạn chat (trong terminal hoặc **qua Telegram**) kiểu *“mở profile Hung NT1”*,
*“kiểm tra kênh A rồi public 3 video private”*.

```
Telegram ─► Hermes (VPS) ──SSH qua Tailscale/NetBird, khóa chỉ chạy được MCP──► profile-ytb-mcp
                                                   ──kết nối nội bộ──► App Profile YTB ──► Chrome
```

**Vì sao an toàn**
- Khóa SSH của Hermes **chỉ chạy được MCP server**: không mở được shell, không forward được cổng.
- Không cần mở cổng nào trên router (Tailscale/NetBird tự kết nối VPS với máy nhà).
- Kết nối điều khiển chỉ nhận từ chính máy này (Ubuntu: socket quyền `600`; Windows: `127.0.0.1`).
- MCP **không có lệnh xóa**.
- Bot Telegram chỉ trả lời Telegram ID nằm trong danh sách cho phép.

**Bước 1: nối VPS với máy nhà** (bỏ qua nếu Hermes chạy trong cùng mạng LAN). Chọn một trong hai:

- [Tailscale](https://tailscale.com/download): cài trên **cả VPS và máy chạy app**, đăng nhập cùng
  một tài khoản. Xem IP bằng `tailscale ip -4`.
- [NetBird](https://netbird.io) (có thể tự host): cài trên **cả 2 máy**, chạy `netbird up` (tự host thì
  thêm `--management-url https://netbird.ten-mien-cua-ban`) với cùng tài khoản/setup key. Xem IP bằng
  `netbird status` (dòng `NetBird IP`). Nếu đã sửa Access Control mặc định, hãy cho phép VPS → máy
  chạy app ở cổng TCP 22.

Máy chạy app sẽ có IP cố định dạng `100.x.y.z`; script ở bước 3 tự phát hiện IP này.

**Bước 2: trên VPS**, tạo khóa riêng cho Hermes:

```bash
ssh-keygen -t ed25519 -N "" -C hermes -f ~/.ssh/hermes_profile_ytb
```

Chép file `~/.ssh/hermes_profile_ytb.pub` sang máy chạy app.

**Bước 3: trên máy chạy app**, cấp quyền cho khóa đó và bật app tự chạy:

| | Ubuntu | Windows (PowerShell, script tự hỏi quyền Administrator) |
|---|---|---|
| Cài SSH server | `sudo apt install openssh-server` | script tự cài OpenSSH Server |
| Cấp quyền khóa | `./scripts/setup_hermes_access.sh hermes_profile_ytb.pub` | `powershell -ExecutionPolicy Bypass -File scripts\setup_hermes_access.ps1 hermes_profile_ytb.pub` |
| App tự chạy khi đăng nhập | `./scripts/install_autostart.sh` | `powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1` |

Script in ra đoạn cấu hình (đã điền sẵn user và IP Tailscale/NetBird). Dán vào `~/.hermes/config.yaml` trên VPS:

```yaml
mcp_servers:
  profile_ytb:
    command: "ssh"
    args: ["-T", "-i", "~/.ssh/hermes_profile_ytb", "-o", "BatchMode=yes",
           "-o", "ServerAliveInterval=30", "ten_user@100.x.y.z"]
    timeout: 300
    connect_timeout: 60
```

Lần đầu, chạy `ssh -i ~/.ssh/hermes_profile_ytb ten_user@100.x.y.z` một lần trên VPS và gõ `yes` để
lưu khóa của máy. Lệnh sẽ đứng chờ vì MCP server đang chờ dữ liệu; bấm `Ctrl+C` để thoát.

> Windows: user thuộc nhóm Administrators thì khóa nằm ở
> `C:\ProgramData\ssh\administrators_authorized_keys` (script tự chọn đúng file).

**Bước 4: cài skill cho Hermes.** Chép thư mục `hermes/profile-ytb/` của dự án vào
`~/.hermes/skills/profile-ytb/` trên VPS. Skill hướng dẫn agent quy trình chuẩn và cách xử lý
từng lỗi. Sau đó mở phiên chat mới, hoặc gõ `/reload-mcp` trong phiên đang chạy.

**Bước 5: điều khiển qua Telegram** (trên VPS)

1. Tạo bot với [@BotFather](https://t.me/BotFather) → lấy **bot token**.
2. Lấy **Telegram ID dạng số** của bạn từ [@userinfobot](https://t.me/userinfobot).
3. Chạy `hermes gateway setup`, chọn Telegram, nhập token và ID. Hoặc tự ghi vào `~/.hermes/.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_ALLOWED_USERS=123456789
   ```
   **Luôn đặt `TELEGRAM_ALLOWED_USERS`**, nếu không ai tìm ra bot cũng điều khiển được Chrome của bạn.
4. Chạy `hermes gateway` (nên chạy như dịch vụ để VPS khởi động lại vẫn tự bật), rồi nhắn bot:
   *“mở profile Hung NT1”*, *“đóng hết Chrome”*, *“public 3 video private cho nhóm A”*.

**Công cụ Hermes nhận được**

| Công cụ | Việc làm |
|---|---|
| `list_profiles` | Liệt kê profile, nhóm, trạng thái |
| `check_channel` | Kiểm tra kênh: số nháp, nháp trùng số, thiếu thumbnail (không đăng) |
| `publish` | Public một profile hoặc cả nhóm (chạy nền, trả về `task_id`) |
| `task_status` | Tiến độ: video thứ mấy, thành công, lỗi, kết quả từng kênh |
| `stop_task` | Dừng sau video đang làm |
| `list_tasks`, `run_task`, `task_history` | Tác vụ có sẵn và lịch sử chạy |
| `open_profiles`, `close_profiles` | Mở/đóng Chrome |

**Giới hạn cho agent.** Thêm vào `settings.json` (Ubuntu: `~/.local/share/chrome-profile-manager/config/`,
Windows: `%LOCALAPPDATA%\ChromeProfileManager\chrome-profile-manager\config\`):

```json
{
  "agent": {
    "allowed_visibility": ["private", "unlisted"],
    "max_videos": 10
  }
}
```

- Mặc định agent được dùng cả 3 chế độ hiển thị, tối đa 20 video mỗi lần.
- Giới hạn chỉ áp dụng cho Hermes. Bạn dùng app hoặc `cpm` thì không bị giới hạn.
- Tác vụ có sẵn do bạn tạo, khi Hermes chạy bằng `run_task`, sẽ dùng đúng cấu hình của tác vụ đó.

**Điều kiện:**
- Máy chạy app bật, **đã đăng nhập** (khóa màn hình thì được, đăng xuất thì không).
- App Profile YTB đang chạy.

Nếu app chưa chạy, Hermes nhận lỗi *“Không kết nối được ứng dụng Profile YTB”* và sẽ báo cho bạn.

## 4. Chạy trên máy Ubuntu khác và build

### Build

```bash
./scripts/install_ubuntu.sh
./scripts/build_ubuntu.sh        # tạo dist/chrome-profile-manager/
./scripts/install_desktop.sh     # (tuỳ chọn) thêm vào menu Applications
```

### Chép sang máy khác

Máy đích không cần Python, chỉ cần Chrome hoặc Chromium. Chép **nguyên thư mục**
`dist/chrome-profile-manager/`, không chỉ file chạy, rồi:

```bash
mkdir -p "$HOME/Applications"
cp -a "/đường/dẫn/dist/chrome-profile-manager" "$HOME/Applications/"
chmod +x "$HOME/Applications/chrome-profile-manager/chrome-profile-manager"
"$HOME/Applications/chrome-profile-manager/chrome-profile-manager"
```

Thêm tham số `--minimized` để khởi động ẩn dưới khay.

---

## 5. Dữ liệu ứng dụng và sao lưu

Mọi dữ liệu nằm tại `~/.local/share/chrome-profile-manager/`:

```text
profiles/   Dữ liệu Chrome của các Profile riêng (mỗi profile một thư mục theo ID)
trash/      (phiên bản cũ) dữ liệu chờ xóa hẳn
database/   SQLite: profile, tác vụ, lịch sử chạy
logs/       app.log (nhật ký, xem ở mục “Nhật ký”) và screenshots/ (ảnh chụp khi public lỗi)
config/     settings.json (cấu hình AI Agent)
```

**Sao lưu** (đóng app và Chrome trước):

```bash
cp -a ~/.local/share/chrome-profile-manager ~/chrome-profile-manager-backup
```

**Chỉ chuyển cấu hình** (không gồm dữ liệu đăng nhập): dùng **Công cụ → Xuất cấu hình ra JSON**,
sau đó **Nhập cấu hình từ JSON** trên máy mới. File nhập được kiểm tra hợp lệ trước khi lưu.

---

## 6. Lỗi thường gặp

| Lỗi | Cách xử lý |
|---|---|
| `Profile chưa đăng nhập YouTube` | Mở profile và đăng nhập YouTube một lần. |
| `Không thấy danh sách video trong YouTube Studio` | Kiểm tra Link Studio của profile. Xem ảnh trong `logs/screenshots/`. |
| `Profile Chrome gốc không hỗ trợ tự động` | Đóng Google Chrome, chuột phải profile → **Chuyển thành Profile riêng (giữ đăng nhập)**, rồi dùng profile mới (mục 3.1). |
| `Xong 0/0 video` | Không có nháp nào có tiêu đề dạng `12 Tên video` trên trang đầu. |
| `bỏ qua N` / `Thiếu thumbnail cho #N` | Thiếu file `N_...jpg` trong thư mục thumbnail, hoặc đặt `"skipMissing": false`. |
| `Trang YouTube Studio bị tải lại hoặc đóng giữa chừng` | Không đóng hoặc tải lại tab Studio khi app đang chạy. |
| `Profile đang được sử dụng bởi tác vụ khác` | Hai tác vụ cùng chạy trên một profile. Đổi giờ chạy cho khác nhau. |
| Tác vụ không chạy đúng giờ | App phải đang mở. Kiểm tra mục 3.7 và cột “Lần chạy kế”. |
| Cột CDP trống | Chưa bật CDP, chưa mở profile lần nào, hoặc đây là profile Chrome gốc. |
| Profile Chrome gốc báo “Đã dừng” dù cửa sổ đang mở | Chrome gốc dùng chung một tiến trình nên không theo dõi riêng từng profile được. Dùng Profile riêng. |
| Không thấy biểu tượng khay | Cài AppIndicator (mục 3.7). |
| App không đọc được profile Chrome | Đừng chạy bằng `sudo`. Kiểm tra `ls ~/.config/google-chrome`. |
| Hermes: `Permission denied (publickey)` | Chạy lại `setup_hermes_access.sh` với đúng file `.pub`, và kiểm tra `-i ~/.ssh/hermes_ubuntu` trong cấu hình Hermes. |
| Hermes: `Host key verification failed` | Chạy `ssh -i ~/.ssh/hermes_ubuntu user@IP` một lần trên laptop, gõ `yes`, rồi `Ctrl+C`. |
| Hermes: `Không kết nối được ứng dụng Profile YTB` | Mở app trên máy Ubuntu, hoặc bật tự khởi động (mục 3.7). |
| Hermes: `Agent không được public ở chế độ …` | Giới hạn trong `settings.json` (mục 3.8). |
| `database is locked` | Hiếm gặp, xảy ra khi app và `cpm` cùng ghi nhiều dữ liệu. Chạy lại lệnh là được. |

---

## 7. Dành cho người phát triển

```bash
. .venv/bin/activate
pytest            # chạy test
ruff check .      # kiểm tra code
```

Cấu trúc chính:

```text
app/main.py                          Khởi động GUI (+ --minimized), socket điều khiển
app/cli.py                           Lệnh cpm
app/mcp_server.py                    MCP server cho Hermes Agent
app/services/controller.py           Mọi lệnh từ bên ngoài + giới hạn cho agent
app/services/control_server.py       Socket điều khiển (/run/user/<uid>/profile-ytb-<mã>.sock)
hermes/profile-ytb/SKILL.md          Skill cho Hermes
app/services/chrome_process_service  Mở/đóng Chrome, phát hiện tiến trình, cổng CDP
app/services/profile_service         Tạo/sửa/xóa vĩnh viễn/nhập-xuất profile
app/services/task_service            Chạy tác vụ: nhóm, thử lại, lịch sử
app/services/scheduler_service       Lịch (APScheduler)
app/services/studio_publisher        Public YouTube qua CDP (mở tab, nạp JS, thumbnail, theo dõi)
app/studio_js/                       Quy trình Studio (JS chép từ extension “bom nguyen tu”)
app/ui/                              Giao diện PySide6
```
