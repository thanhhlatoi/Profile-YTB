---
name: profile-ytb
description: Public video nháp YouTube trên nhiều kênh qua Profile YTB (Chrome Profile Manager) chạy trên máy Windows/Ubuntu của người dùng. Dùng khi người dùng muốn kiểm tra kênh, public/lên lịch video nháp, xem tiến độ hoặc dừng việc public.
---

# Profile YTB: public video YouTube

Các công cụ đến từ MCP server `profile_ytb` (máy Windows/Ubuntu của người dùng, qua SSH).
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
