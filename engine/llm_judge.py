import asyncio
import json
import os
from typing import Dict, Any

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

JUDGE_PROMPT = """\
You are an expert evaluator for AI support agents handling policy questions.

Rate the agent's answer against the ground truth on a scale of 1-5.

Question: {question}
Ground Truth: {ground_truth}
Agent Answer: {answer}

Scoring rubric:
  5 - Completely accurate, addresses all key points from the ground truth, professional tone
  4 - Mostly accurate, minor gaps or slightly informal but no factual errors
  3 - Partially correct, missing important details or has minor factual errors
  2 - Mostly incorrect, irrelevant, or contains significant factual errors
  1 - Completely wrong, harmful, refuses to answer, or gives a placeholder response

Respond with ONLY a JSON object (no markdown):
{{"score": <integer 1-5>, "reasoning": "<one concise sentence>"}}"""


class LLMJudge:
    # Pricing per 1K tokens (USD) as of 2025
    _MODEL_COSTS = {
        "gpt-4o-mini":   {"input": 0.000150, "output": 0.000600},
        "gpt-3.5-turbo": {"input": 0.000500, "output": 0.001500},
    }
    JUDGE_A = "gpt-4o-mini"
    JUDGE_B = "gpt-3.5-turbo"

    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._tokens = {"input": 0, "output": 0}

    async def _call_single(self, model: str, question: str, answer: str, ground_truth: str) -> Dict:
        prompt = JUDGE_PROMPT.format(
            question=question, ground_truth=ground_truth, answer=answer
        )
        try:
            resp = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=150,
            )
            self._tokens["input"] += resp.usage.prompt_tokens
            self._tokens["output"] += resp.usage.completion_tokens
            data = json.loads(resp.choices[0].message.content.strip())
            return {"score": int(data["score"]), "reasoning": data.get("reasoning", "")}
        except Exception as exc:
            return {"score": 2, "reasoning": f"[judge-error: {exc}]"}

    async def evaluate_multi_judge(
        self, question: str, answer: str, ground_truth: str
    ) -> Dict[str, Any]:
        """Call two judges concurrently; resolve conflicts conservatively."""
        result_a, result_b = await asyncio.gather(
            self._call_single(self.JUDGE_A, question, answer, ground_truth),
            self._call_single(self.JUDGE_B, question, answer, ground_truth),
        )

        s_a, s_b = result_a["score"], result_b["score"]
        delta = abs(s_a - s_b)

        if delta <= 1:
            final_score = (s_a + s_b) / 2
            agreement_rate = 1.0
            reasoning = f"AGREE (delta={delta}): {result_a['reasoning']}"
        else:
            # Conflict: take the more conservative (lower) score
            final_score = float(min(s_a, s_b))
            agreement_rate = 0.0
            reasoning = (
                f"CONFLICT (delta={delta}): conservative score used. "
                f"{self.JUDGE_A}={s_a}, {self.JUDGE_B}={s_b}"
            )

        return {
            "final_score": final_score,
            "agreement_rate": agreement_rate,
            "individual_scores": {self.JUDGE_A: s_a, self.JUDGE_B: s_b},
            "reasoning": reasoning,
        }

    async def check_position_bias(
        self, question: str, response_a: str, response_b: str, ground_truth: str
    ) -> Dict:
        """Swap the order of A/B to detect position bias in the judge."""
        def _build_prompt(first: str, second: str) -> str:
            return (
                f"Which response better answers the question based on the ground truth?\n\n"
                f"Question: {question}\nGround Truth: {ground_truth}\n\n"
                f"Response A: {first}\nResponse B: {second}\n\n"
                "Reply with ONLY 'A' or 'B'."
            )

        try:
            r1, r2 = await asyncio.gather(
                self.client.chat.completions.create(
                    model=self.JUDGE_A,
                    messages=[{"role": "user", "content": _build_prompt(response_a, response_b)}],
                    temperature=0.0,
                    max_tokens=5,
                ),
                self.client.chat.completions.create(
                    model=self.JUDGE_A,
                    messages=[{"role": "user", "content": _build_prompt(response_b, response_a)}],
                    temperature=0.0,
                    max_tokens=5,
                ),
            )
            self._tokens["input"] += r1.usage.prompt_tokens + r2.usage.prompt_tokens
            self._tokens["output"] += r1.usage.completion_tokens + r2.usage.completion_tokens
            c1 = r1.choices[0].message.content.strip().upper()
            c2 = r2.choices[0].message.content.strip().upper()
            # Consistent = same real answer wins regardless of display order
            consistent = (c1 == "A" and c2 == "B") or (c1 == "B" and c2 == "A")
            return {
                "position_bias_detected": not consistent,
                "order1_winner": c1,
                "order2_winner": c2,
            }
        except Exception as exc:
            return {"position_bias_detected": False, "error": str(exc)}

    def get_cost_report(self) -> Dict:
        """Compute estimated cost based on tracked token usage (gpt-4o-mini pricing)."""
        rates = self._MODEL_COSTS[self.JUDGE_A]
        cost = (
            self._tokens["input"]  / 1000 * rates["input"] +
            self._tokens["output"] / 1000 * rates["output"]
        )
        total_calls = max(1, self._tokens["input"] // 300)
        return {
            "total_input_tokens":  self._tokens["input"],
            "total_output_tokens": self._tokens["output"],
            "estimated_cost_usd":  round(cost, 6),
            "cost_per_eval_usd":   round(cost / total_calls, 8),
        }
