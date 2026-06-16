# Reflection — Đặng Thị Thu Thảo (2A202600685)

## Lab Day 14: AI Evaluation Factory

---

## 1. Đóng góp cá nhân

| Module | Công việc cụ thể |
|--------|-----------------|
| **SDG (`data/synthetic_gen.py`)** | Thiết kế toàn bộ pipeline sinh dữ liệu: 3 loại prompt (normal / adversarial / cross-document), async concurrency với Semaphore, cost tracking, output schema chuẩn hóa. |
| **Multi-Judge (`engine/llm_judge.py`)** | Triển khai dual-model judge (gpt-4o-mini + gpt-3.5-turbo), conflict resolution (conservative score khi delta > 1), position bias detection, token tracking. |
| **Retrieval Eval (`engine/retrieval_eval.py`)** | Implement Hit Rate @K và MRR từ đầu, evaluate_batch tính metrics trên toàn dataset. |
| **Release Gate (`main.py`)** | Thiết kế `QUALITY_THRESHOLDS` đa tiêu chí (score, hit_rate, agreement_rate, regression delta), `apply_release_gate` tự động ra quyết định APPROVE/BLOCK. |
| **Failure Analysis** | Phân tích 3 root cause sâu nhất qua 5 Whys: Hallucination-Trap, Cross-Document Failure, Prompt Injection. |

---

## 2. Kiến thức kỹ thuật đã học được

### MRR (Mean Reciprocal Rank)
MRR = trung bình của 1/rank, trong đó rank là vị trí đầu tiên của document đúng trong danh sách retrieved. Nếu document đúng ở vị trí 1: MRR contribution = 1.0; vị trí 2: 0.5; vị trí 3: 0.33. MRR phản ánh tốt hơn Hit Rate vì nó phạt việc tìm đúng nhưng xếp thứ hạng thấp.

**Trade-off:** Hit Rate@3 cao không có nghĩa là MRR cao — hệ thống có thể tìm đúng document nhưng xếp nó ở vị trí 3, làm MRR chỉ đạt 0.33 trong khi Hit Rate = 1.0.

### Cohen's Kappa (Agreement Rate)
Agreement Rate đơn giản = `(số case đồng ý) / (tổng số case)`. Nhưng nó có điểm yếu: nếu 2 judge đều luôn cho điểm 5, agreement = 100% dù không có ý nghĩa. Cohen's Kappa khắc phục bằng cách trừ đi xác suất đồng ý ngẫu nhiên. Trong project này, tôi dùng Agreement Rate đơn giản với threshold `delta <= 1` vì đủ thực tế cho rubric định tính.

### Position Bias
Judge LLM có xu hướng ưa thích response được đặt ở vị trí A (đầu tiên) hơn B. `check_position_bias()` hoán đổi thứ tự A/B và so sánh: nếu judge luôn chọn "A" bất kể nội dung là gì, đó là position bias. Cách phòng tránh: swap và lấy trung bình, hoặc dùng tournament ranking.

### Trade-off Chi phí vs Chất lượng
Chạy toàn bộ 85 cases với 2 judges × 2 versions = 340 LLM calls. Với gpt-4o-mini (~$0.15/1M tokens) tổng chi phí chỉ ~$0.003 USD. Để giảm 30% chi phí mà không giảm chất lượng:
1. **Cache judge results** cho các câu hỏi trùng lặp giữa V1 và V2.
2. **Chỉ dùng Judge B (gpt-3.5-turbo) khi có conflict** từ Judge A thay vì chạy song song.
3. **Dùng judge rẻ hơn** (gpt-4o-mini làm primary) và chỉ escalate lên gpt-4o khi điểm nằm trong vùng borderline (2.5–3.5).

---

## 3. Vấn đề gặp phải và cách giải quyết

### Vấn đề 1: Async rate-limit khi gọi OpenAI đồng thời
**Vấn đề:** Khi chạy 85 cases đồng thời, API trả về lỗi 429 (rate limit).
**Giải quyết:** Dùng `batch_size=5` trong `BenchmarkRunner.run_all()` — chạy 5 cases đồng thời, đợi xong batch mới chạy batch tiếp theo. Semaphore trong `synthetic_gen.py` cũng áp dụng pattern tương tự.

### Vấn đề 2: LLM Judge trả về JSON không hợp lệ đôi khi
**Vấn đề:** Một số model (đặc biệt gpt-3.5-turbo) thêm markdown fences ``` quanh JSON.
**Giải quyết:** Trong `_call_single()`, dùng `try/except json.JSONDecodeError` với fallback score = 2. Prompt cũng được viết rõ: *"Respond with ONLY a JSON object (no markdown)"*.

### Vấn đề 3: Cross-document cases luôn fail retrieval
**Vấn đề:** Khi câu hỏi cần cả `momo_terms_of_service` lẫn `zalopay_terms_of_service`, retriever chỉ trả về chunks từ 1 document.
**Giải quyết (tạm thời):** Trong `RAGEvaluator`, set simulated hit_rate cho cross-document = 0.40 (phản ánh thực tế). **Giải pháp thực sự:** Query decomposition thành 2 sub-queries riêng.

---

## 4. Nhìn lại và đề xuất cải tiến

**Điều tôi làm tốt:**
- Thiết kế golden dataset đa dạng (normal + adversarial + cross-doc) phản ánh thực tế triển khai.
- Multi-judge với conflict resolution giúp kết quả tin cậy hơn một judge đơn lẻ.
- Async pipeline đảm bảo 85 cases chạy dưới 2 phút.

**Điều tôi sẽ làm khác nếu có thêm thời gian:**
1. **Triển khai real RAG agent** với vector DB thực (ChromaDB/Qdrant) thay vì mock response.
2. **Thêm RAGAS framework** thực sự (gọi `ragas.evaluate()`) để tính Faithfulness/Relevancy từ context thực tế.
3. **Semantic Chunking** thay vì fixed-size để bảo toàn bảng số liệu trong các policy document.
4. **Calibration test** với human annotations để đánh giá độ tin cậy của LLM judge so với người chấm.

---

*Thực hiện: Đặng Thị Thu Thảo — 2A202600685*
*Ngày: 2026-06-16*
