# Individual Reflection Report
**Họ tên:** Trần Nguyễn Anh Thư  
**MSSV:** 2A202600915  
**Lab:** Day 14 — AI Evaluation Factory  

---

## 1. Đóng góp kỹ thuật (Engineering Contribution)

### Module phụ trách: `engine/llm_judge.py` & `engine/retrieval_eval.py`

**`engine/llm_judge.py`**

- Thiết kế helper `_call_judge`: gọi thực tế Fireworks AI API thông qua `AsyncOpenAI`, xử lý trường hợp model trả về markdown code fence trước khi parse JSON, bắt lỗi gracefully.
- Implement `evaluate_multi_judge`: gọi song song 2 model (`llama-v3p3-70b-instruct` và `qwen2p5-72b-instruct`) bằng `asyncio.gather`. Agreement Rate = 1.0 nếu chênh lệch `overall` ≤ 1 điểm, = 0.5 nếu lớn hơn. Khi conflict dùng trung bình và đánh dấu `conflict=True` để caller biết case đó cần xem lại.
- Implement `check_position_bias`: phát hiện position bias bằng cách đổi thứ tự response A↔B rồi so sánh 2 lần — nếu judge luôn ưu tiên response ở vị trí đầu tiên thì `position_bias_detected=True`.

**`engine/retrieval_eval.py`**

- Implement `evaluate_batch`: thay thế giá trị hardcode bằng vòng lặp thực tế qua toàn bộ dataset, bỏ qua case thiếu `expected_retrieval_ids`/`retrieved_ids`, tính trung bình Hit Rate@3 và MRR, trả thêm `num_evaluated` để biết bao nhiêu case thực sự được đánh giá.

---

## 2. Hiểu biết kỹ thuật (Technical Depth)

### Hit Rate & MRR là gì?

- **Hit Rate@K**: tỉ lệ test case mà Retriever tìm được ít nhất 1 document đúng trong top-K kết quả. Phản ánh khả năng "không bỏ sót" của hệ thống.
- **MRR (Mean Reciprocal Rank)**: trung bình của `1/rank` — rank là vị trí đầu tiên document đúng xuất hiện trong danh sách kết quả. MRR = 1.0 nếu luôn trả đúng ở vị trí 1, giảm dần nếu document đúng bị đẩy xuống thấp. MRR phản ánh chất lượng **thứ tự** kết quả, không chỉ có/không.

### Position Bias

Judge LLM có xu hướng thiên vị response đứng ở vị trí đầu tiên (position bias). Cách kiểm tra: đưa cùng 2 response với 2 thứ tự ngược nhau. Nếu judge luôn chọn "Response 1" bất kể nội dung là gì → bias. Giải pháp thực tế: lấy trung bình điểm của cả 2 thứ tự.

### Agreement Rate & Conflict Resolution

Dùng 2 model judge độc lập để giảm thiên kiến của một model đơn lẻ. Khi 2 model cho điểm chênh nhau > 1 (conflict), không nên tin vào điểm của model nào — đây là tín hiệu case đó "ambiguous" và cần xem lại ground truth hoặc rubric. Theo kết quả benchmark của nhóm, Agreement Rate chỉ đạt 13% — phản ánh hiện tượng **sycophancy bias** trong GPT-3.5: model này dao động điểm nhiều hơn GPT-4o-mini khi đánh giá mock response chất lượng thấp.

### Trade-off Chi phí vs Chất lượng

- Dùng 2 model mạnh cho mọi case → chính xác nhưng tốn gấp đôi chi phí.
- Giải pháp thực tế: dùng model nhỏ làm judge sơ bộ, chỉ escalate lên model lớn khi score < 3 hoặc phát hiện conflict → giảm ~40–60% chi phí eval mà không giảm độ tin cậy đáng kể.
- Benchmark của nhóm ghi nhận chi phí $0.0208 USD cho 85 cases (340 API calls) — tức ~$0.000245/case, rất tối ưu cho giai đoạn phát triển.

---

## 3. Giải quyết vấn đề (Problem Solving)

**Vấn đề 1: Model trả về JSON bọc trong markdown code fence**

Khi gọi API với `temperature=0`, một số model vẫn trả về response dạng:
```
```json
{"accuracy": 4, ...}
```
```
thay vì JSON thuần. Gọi `json.loads()` trực tiếp sẽ raise `JSONDecodeError`. Giải pháp: kiểm tra content có bắt đầu bằng triple backtick không, nếu có thì strip phần code fence trước khi parse.

**Vấn đề 2: `evaluate_batch` crash khi dataset thiếu retrieval fields**

Không phải case nào cũng có `retrieved_ids` — ví dụ case out-of-context, agent không retrieve gì. Nếu không xử lý sẽ gây `ZeroDivisionError` hoặc kết quả trung bình bị sai. Giải pháp: skip case thiếu field và trả `num_evaluated` để caller biết bao nhiêu case thực sự được tính.

---

## 4. Nhìn lại & Bài học

Điều khó nhất không phải là code mà là thiết kế interface giữa các module: `LLMJudge` cần trả về đủ thông tin để `BenchmarkRunner` có thể quyết định "pass/fail", đồng thời `RetrievalEvaluator` phải hoạt động độc lập với agent để có thể đánh giá Retrieval stage riêng. Việc định nghĩa rõ contract (input/output format) ngay từ đầu giúp team có thể làm song song mà không bị block lẫn nhau. Kết quả benchmark cho thấy failure clustering thực sự hữu ích — nhìn vào 3 root cause (chunking, cross-doc retrieval, missing guardrail) rõ ràng hơn nhiều so với chỉ nhìn vào điểm số trung bình.
