---
name: profile-ytb
description: Tải video YouTube (kèm sub, thumbnail) về máy Windows của người dùng, chọn ổ E/F, thư mục, số thứ tự video, ngôn ngữ phụ đề; và public video nháp YouTube trên nhiều kênh qua Profile YTB. ĐÂY LÀ CÁCH TẢI MẶC ĐỊNH khi người dùng gửi link YouTube; chỉ dùng skill ytnas khi người dùng nói rõ chữ NAS.
---

# Profile YTB: public video YouTube

Các công cụ đến từ MCP server `profile_ytb` (máy Ubuntu) và `profile_ytb_win` (máy Windows,
qua SSH). Các tool tải video (`download_video`, `download_batch`, `download_status`,
`download_stop`, `download_locations`) chỉ có ở `profile_ytb_win`.
Luôn trả lời người dùng bằng tiếng Việt.

## Khi người dùng hỏi tình hình kênh (không đăng gì)

1. `list_profiles` để lấy tên profile.
2. `channel_status(profile)`: profile đang mở không, chế độ hiển thị mặc định, lần đăng gần nhất.
3. `check_channel(profile)` nếu cần số nháp, nháp trùng số, nháp thiếu thumbnail.
Hai tool này chỉ đọc. Không gọi `publish` nếu người dùng không yêu cầu.

## Quy trình chuẩn

1. `list_profiles` để lấy đúng tên profile hoặc nhóm. Không tự đoán tên.
2. `check_channel(profile)` cho từng kênh sắp đăng. Báo người dùng:
   số nháp, các số thứ tự, nháp thiếu thumbnail (`missing_thumbnails`),
   nháp trùng số (`duplicate_draft_indexes`), chế độ hiển thị (`visibility`).
   - Nếu có `duplicate_draft_indexes`: **dừng**, yêu cầu người dùng sửa tiêu đề trong Studio.
   - Nếu `draft_count` là 0: báo không có gì để đăng.
3. Chỉ gọi `publish` khi người dùng đã yêu cầu rõ ràng. Nếu người dùng không nói chế độ
   hiển thị thì để trống (dùng cấu hình của profile) và nói rõ chế độ đó trong câu trả lời.
4. `publish` trả về `task_id` ngay. Gọi `task_status(task_id)` mỗi 30–60 giây cho tới khi
   `finished` là `true`. Trong lúc chờ, có thể báo tiến độ từ `progress`
   (`currentIndex`/`totalVideos`, `success`, `failed`).
5. Báo kết quả theo từng kênh từ `runs`: `result` (ví dụ "Xong 5/6 video, bỏ qua 1") hoặc `error`.

## Xử lý lỗi

| Lỗi chứa | Việc cần làm |
|---|---|
| `Không kết nối được ứng dụng Profile YTB` | App chưa chạy trên máy người dùng. Nhờ người dùng mở app. Không thử lại liên tục. |
| `chưa đăng nhập YouTube` | Người dùng phải mở profile đó và đăng nhập. Agent không làm được. |
| `Không thấy danh sách video` | Link Studio của profile sai hoặc YouTube chậm. Thử lại `check_channel` **một** lần, sau đó báo người dùng (kèm đường dẫn ảnh chụp nếu có). |
| `Agent không được public ở chế độ` | Chính sách giới hạn. Báo người dùng, không tự đổi sang chế độ khác. |
| `Profile đang được sử dụng bởi tác vụ khác` | Đang có việc khác chạy trên kênh đó. Chờ, hoặc xem `list_tasks`. |
| `Thiếu thumbnail` / `bỏ qua` | Không phải lỗi hệ thống. Liệt kê các số thứ tự thiếu ảnh. |
| `lỗi N` trong kết quả | Liệt kê từng `#số: lý do`. Không tự chạy lại toàn bộ (tránh đăng trùng). |

## Quy tắc an toàn

- Không bao giờ public lặp lại cùng một kênh khi tác vụ trước chưa `finished`.
- Muốn dừng: `stop_task(task_id)`. Video đang làm sẽ xong rồi mới dừng.
- Không có công cụ xóa; đừng hướng dẫn người dùng xóa dữ liệu để "sửa lỗi".

## Tải video YouTube

Đây là cách tải **mặc định**. Chỉ khi tin nhắn có chữ "NAS" mới dùng skill `ytnas`. Tuyệt đối
không dùng lệnh `ytnas` cho yêu cầu có ổ E/F hoặc không nhắc NAS.

Khi người dùng gửi link YouTube (video, playlist hoặc kênh) và muốn tải:

1. Một link: `download_video(url, sub_lang, range, folder)`. Nhiều link trong cùng tin nhắn:
   `download_batch(urls, sub_lang, range, folder)` (tối đa 20, tối đa 2 job chạy cùng lúc, còn lại xếp hàng).
   - `sub_lang` = mã ngôn ngữ phụ đề, mặc định `en`. Người dùng nói tên ngôn ngữ thì tự đổi
     sang mã, không hỏi lại: Anh `en`, Nhật `ja`, Hàn `ko`, Trung giản thể `zh-Hans`, Trung phồn
     thể `zh-Hant`, Việt `vi`, Pháp `fr`, Đức `de`, Tây Ban Nha `es`, Bồ Đào Nha `pt`, Ý `it`,
     Nga `ru`, Thái `th`, Indonesia `id`, Ả Rập `ar`, Hindi `hi`. Nhiều ngôn ngữ thì ngăn bằng
     dấu phẩy không có khoảng trắng, ví dụ `en,ja`. Ngôn ngữ khác thì dùng mã ISO 639-1.
     Không dùng `all` (hàng trăm bản dịch tự động, dễ bị YouTube chặn); nếu người dùng muốn
     "tất cả phụ đề" thì hỏi lại họ cần những ngôn ngữ nào.
   - Phụ đề lấy bản do người đăng, nếu không có thì bản tự động của YouTube. Video không có
     phụ đề ngôn ngữ đó thì vẫn tải video, chỉ không có file `.srt`; báo rõ cho người dùng.
   - `range` như `1-5` = tải video số 1 đến 5 của kênh/playlist (1 là mới nhất); chỉ dùng cho
     kênh/playlist. "5 video mới nhất" = `1-5`. Không tự đoán nếu người dùng không nói số.
   - `drive` = ổ đĩa người dùng nói ("ổ E", "ổ F", "drive E") → truyền `E`, `F`. Chỉ nhận các ổ
     trong `download_locations()` (hiện có mặc định C, E, F). Người dùng không nói ổ thì để trống
     (lưu vào nơi mặc định) và nói rõ đã lưu ở đâu. Người dùng hỏi "lưu được ở đâu / ổ nào còn
     trống" thì gọi `download_locations()` rồi trả lời kèm dung lượng trống. Ổ không có trong
     danh sách (ví dụ ổ D, ổ Z) hoặc đường dẫn kiểu `E:\abc` thì không làm theo; giải thích chỉ
     chọn được các ổ trong danh sách, và thư mục con thì đặt bằng `folder`.
   - `folder` = tên thư mục con (nằm trong ổ đã chọn) người dùng muốn lưu vào (ví dụ "Drama"); chỉ chữ, số, khoảng
     trắng, gạch ngang. Không nói thì để trống. Không nhận đường dẫn ổ đĩa; nếu người dùng đưa
     đường dẫn thì giải thích chỉ chọn được tên thư mục con trong thư mục tải.
   - Không tự đoán link. Chỉ nhận link YouTube.
2. Tool trả về `job_id` ngay. Gọi `download_status()` (bỏ trống job) mỗi 30–60 giây cho tới khi
   mọi job có `finished` là `true`. Không gọi lại tool tải cho cùng link khi job chưa xong.
3. Chỉ báo "xong" khi `download_status` trả `finished` là `true` và `status` là `SUCCESS`. Mới
   gọi `download_video`/`download_batch` (nhận `job_id`) nghĩa là CHƯA tải xong; nói "đã bắt đầu
   tải" và tiếp tục theo dõi. Báo kết quả từng link: `status`, thư mục đã lưu (`folders`), số file (`moved`). Nếu `note`
   nói không có video mới thì video đã tải trước đó (nằm trong archive), không phải lỗi.
4. Muốn dừng: `download_stop(job_id)`. Tối đa 2 job chạy song song, job còn lại ở QUEUED chờ tới lượt.
5. `FAILED` kèm lỗi 403 hoặc "Sign in to confirm": cookies hết hạn, nhờ người dùng xuất lại
   `cookies.txt`. Báo lỗi, không thử lại liên tục.
6. `Chưa có ytdlp/cookies`: bộ tải chưa được cài trên máy; báo người dùng chạy
   `scripts\setup_downloader.ps1`.
