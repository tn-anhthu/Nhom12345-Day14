# Individual Reflection Report
**Họ tên:** Nguyễn Phan Duy Bảo
**MSSV:** 2A202600688
**Lab:** Day 14 — AI Evaluation Factory (Expert Level)
**Ngày:** 2026-06-16

---

## 1. Đóng góp kỹ thuật (Engineering Contribution)

Tôi phụ trách phần **Data** — tức là nền móng của cả hệ thống eval: (1) **crawl/thu thập các chính sách (Terms of Service & Privacy Policy) của các nền tảng Việt Nam và chuẩn hóa thành file markdown/txt**, và (2) **xây dựng pipeline sinh test cases (SDG) để tạo Golden Dataset**. Không có knowledge base sạch và golden set chất lượng thì mọi metric phía sau (Hit Rate, faithfulness, judge score) đều vô nghĩa.

### A. Crawl & chuẩn hóa knowledge base (`data/policy/`)
- Thu thập các tài liệu chính sách (gồm cả *terms of service* lẫn *privacy policy*) từ nhiều nền tảng Việt Nam.
- Crawl HTML thô → bóc tách nội dung chính → **chuẩn hóa thành markdown/txt** sạch (bỏ menu/nav/script, giữ heading và cấu trúc điều khoản), đặt `doc_id` theo tên file để dùng làm khóa Ground Truth.

### B. Synthetic Data Generation (`data/synthetic_gen.py`)
- Thiết kế pipeline SDG sinh **85 test cases** từ 15 document, mỗi case đúng schema golden set: `id`, `question`, `expected_answer`, `context` (trích dẫn gốc), `ground_truth_doc_ids`, và `metadata` (difficulty/type/source_file/adversarial).
- Viết **3 loại prompt sinh dữ liệu** riêng biệt:
  - `NORMAL_PROMPT` — QA bám sát text, ép có ≥1 câu numerical và ≥1 câu hard mỗi document.
  - `ADVERSARIAL_PROMPT` — red-teaming: out-of-scope, ambiguous, hallucination-trap, prompt-injection (15 case adversarial).
  - `CROSS_DOC_PROMPT` — câu hỏi cần thông tin từ **2 document** (5 cặp × 2 = 10 case cross-document), ghi cả 2 `doc_id` vào `ground_truth_doc_ids` để đo Hit Rate đa nguồn.
- **Async + Semaphore(5)** để gọi LLM song song mà không bị rate-limit; có **cost tracking** (đếm input/output token, quy ra USD).
- Viết `parse_json_response()` chống lỗi format (strip markdown fence, fallback regex tìm khối `[...]`) và `build_case()` chuẩn hóa output, đảm bảo `check_lab.py` đọc được.

**Kết quả Golden Dataset (đo thực tế):**

| Chiều phân bố | Giá trị |
|---|---|
| Tổng số cases | **85** (≥ 50 yêu cầu) |
| Documents phủ | **15/15** |
| Difficulty | easy 29 · medium 16 · hard 25 · adversarial 15 |
| Type | fact-check 20 · numerical 15 · procedural 14 · hallucination-trap 10 · cross-document 10 · definition 7 · out-of-scope 4 · comparison 4 · prompt-injection 1 |
| Red-teaming (adversarial) | 15 case |

---

## 2. Hiểu biết kỹ thuật (Technical Depth)

### Tại sao Ground Truth IDs là điều kiện để đo Hit Rate & MRR
Mỗi case tôi sinh ra đều gắn `ground_truth_doc_ids` — đây chính là "đáp án" để chấm tầng Retrieval. **Hit Rate@K** = tỉ lệ case mà retriever lấy được ít nhất 1 document đúng trong top-K. **MRR (Mean Reciprocal Rank)** = trung bình `1/rank` với rank là vị trí đầu tiên document đúng xuất hiện (vị trí 1 → 1.0, vị trí 2 → 0.5, vị trí 3 → 0.33). Khác biệt: Hit Rate chỉ trả lời "có lấy đúng không", còn MRR phạt việc lấy đúng nhưng xếp hạng thấp. Vì tôi gán đúng `doc_id` cho từng case (kể cả 2 id cho cross-document), nhóm mới tách bạch được lỗi: hit_rate nhóm đạt **72.9%** — nghĩa là ~27% case retriever trượt document đúng, và đó là gốc rễ của hallucination chứ không phải lỗi của LLM sinh câu trả lời.

### Vai trò của dataset với Cohen's Kappa / Agreement Rate
Agreement Rate đơn giản = `số case 2 judge đồng thuận / tổng case`. Nhược điểm: nếu dataset toàn câu dễ, cả 2 judge đều cho điểm cao → agreement ảo cao mà vô nghĩa. **Cohen's Kappa** (`κ = (p_o − p_e)/(1 − p_e)`) trừ đi xác suất đồng thuận ngẫu nhiên nên đáng tin hơn. Chính vì vậy tôi cố ý **trộn độ khó** (29 easy ↔ 25 hard ↔ 15 adversarial): dataset có đủ case borderline thì Agreement Rate 85.9% của nhóm mới phản ánh độ tin cậy thật, và phần conflict 14% rơi đúng vào vùng hard/adversarial — nơi hai judge calibrate khác nhau.

### Position Bias & Red-teaming
Position bias là việc judge thiên vị response đặt ở vị trí đầu. Bộ adversarial tôi tạo (đặc biệt hallucination-trap: nhúng số sai vào câu hỏi như *"giới hạn giao dịch MoMo có phải 200.000.000đ không?"*) chính là loại case giúp lộ ra agent có sycophancy/hallucination hay không — và là input cần thiết để các test position bias/conflict resolution có dữ liệu khó để chạy.

### Trade-off Chi phí vs Chất lượng (ở tầng sinh dữ liệu)
Sinh 85 case bằng LLM tốn token thật, nên tôi tối ưu: `truncate()` document xuống ~6000 ký tự (cross-doc 2500) trước khi đưa vào prompt để cắt input token, gộp nhiều câu hỏi trong **1 lần gọi/doc** thay vì 1 call/câu, và chạy async để giảm thời gian. Cách giảm thêm ~30% chi phí mà giữ chất lượng: cache theo `doc_id` (không sinh lại khi policy không đổi) và chỉ dùng model mạnh cho document phức tạp, model rẻ cho document ngắn.

---

## 3. Giải quyết vấn đề (Problem Solving)

**Vấn đề 1: Document quá dài, vượt context window khi sinh QA**
Các file như `grab-billing-terms.md` (~72KB) không thể nhét trọn vào 1 prompt. Tôi viết `truncate()` cắt theo ranh giới câu (tìm dấu `.` cuối cùng) thay vì cắt cứng giữa từ, giữ ngữ cảnh mạch lạc để LLM sinh câu hỏi/đáp án không bị đứt nghĩa.

**Vấn đề 2: LLM trả JSON kèm markdown fence → parse fail**
Model hay bọc kết quả trong ` ```json ... ``` `. Nếu `json.loads()` trực tiếp sẽ crash và mất nguyên batch. Tôi viết `parse_json_response()` 2 lớp: strip fence bằng regex, nếu vẫn lỗi thì fallback tìm khối `[...]` đầu tiên, và log cảnh báo thay vì raise — đảm bảo một document hỏng không làm sập cả pipeline 15 document.

**Vấn đề 3: Crawl ra nội dung rác (menu, script, footer)**
HTML thô lẫn rất nhiều thành phần không phải nội dung chính sách. Tôi chuẩn hóa thủ công + bóc tách về markdown giữ heading/điều khoản, vì nếu để rác trong knowledge base thì chunk sẽ chứa nhiễu, kéo tụt Hit Rate và làm câu hỏi sinh ra bị lệch khỏi nội dung thật.

**Vấn đề 4: Cross-document case rất khó sinh tự động**
LLM có xu hướng chỉ trả lời từ 1 document. Tôi giải bằng cách thiết kế `CROSS_DOC_PROMPT` đưa **đồng thời 2 document** và yêu cầu rõ "câu hỏi phải cần cả hai", đồng thời gán cả 2 `doc_id` vào ground truth — nhờ vậy nhóm mới benchmark được đúng nhóm lỗi "cross-document retrieval failure" (40% số case fail).

---

## 4. Nhìn lại & Bài học

Bài học lớn nhất: **chất lượng eval bị giới hạn bởi chất lượng dữ liệu, không phải bởi code đánh giá.** Lúc đầu tôi nghĩ phần data chỉ là "chuẩn bị", nhưng khi benchmark chạy ra hit_rate 72.9% (dưới ngưỡng gate 80%) và 35% case fail, chính nhờ `ground_truth_doc_ids` và phân loại difficulty/type tôi gắn cho từng case mà nhóm mới *clustering* được lỗi (chunking cắt bảng số liệu, cross-doc retrieval, prompt-injection) thay vì chỉ nhìn một con số trung bình. Một golden set không có ground truth IDs hoặc thiếu adversarial case thì cả hệ eval sẽ "mù".

Nếu có thêm thời gian, tôi sẽ: (1) viết crawler tự động hóa hoàn toàn (Playwright) thay cho việc chuẩn hóa bán thủ công; (2) thêm bước **human-in-the-loop verify** một mẫu golden case để đo độ chính xác của SDG; (3) bổ sung case **conflicting-information** và **multi-turn** theo HARD_CASES_GUIDE để dataset bám sát kịch bản thật hơn.

---

*Thực hiện: Nguyễn Phan Duy Bảo — 2A202600688*
