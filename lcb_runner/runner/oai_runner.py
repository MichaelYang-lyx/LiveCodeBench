import os
from time import sleep

try:
    import openai
    from openai import OpenAI
except ImportError as e:
    pass

from lcb_runner.lm_styles import LMStyle
from lcb_runner.runner.base_runner import BaseRunner
from lcb_runner.utils.token_records import append_token_record, compute_tokens


class OpenAIRunner(BaseRunner):
    client = OpenAI(
        api_key=os.getenv("OPENAI_KEY"),
        base_url=os.getenv("OPENAI_API_BASE") or None,
    )

    def __init__(self, args, model):
        super().__init__(args, model)
        if model.model_style == LMStyle.OpenAIReasonPreview:
            self.client_kwargs: dict[str | str] = {
                "model": args.model,
                "max_completion_tokens": 25000,
            }
        elif model.model_style == LMStyle.OpenAIReason:
            assert (
                "__" in args.model
            ), f"Model {args.model} is not a valid OpenAI Reasoning model as we require reasoning effort in model name."
            model_id, reasoning_effort = args.model.split("__", 1)
            STANDARD_EFFORTS = {"low", "medium", "high"}
            if reasoning_effort in STANDARD_EFFORTS:
                self.client_kwargs: dict[str | str] = {
                    "model": model_id,
                    "reasoning_effort": reasoning_effort,
                }
            else:
                self.client_kwargs: dict[str | str] = {
                    "model": model_id,
                    "extra_body": {"reasoning_effort": reasoning_effort},
                }
        elif args.model.startswith("claude"):
            self.client_kwargs: dict[str | str] = {
                "model": args.model,
                "max_tokens": args.max_tokens,
                "timeout": args.openai_timeout,
            }
        else:
            self.client_kwargs: dict[str | str] = {
                "model": args.model,
                "temperature": args.temperature,
                "max_tokens": args.max_tokens,
                "top_p": args.top_p,
                "frequency_penalty": 0,
                "presence_penalty": 0,
                "n": args.n,
                "timeout": args.openai_timeout,
                # "stop": args.stop, --> stop is only used for base models currently
            }

    def _run_single(self, prompt: list[dict[str, str]], n: int = 10, task_id: str | None = None) -> list[str]:
        assert isinstance(prompt, list)

        if n == 0:
            print("Max retries reached. Returning empty response.")
            return []

        try:
            use_stream = getattr(self.args, "stream", False)
            if use_stream:
                # 流式：按 choice.index 分桶累加 delta.content / delta.reasoning
                n_out = self.client_kwargs.get("n", 1)
                stream = OpenAIRunner.client.chat.completions.create(
                    messages=prompt,
                    stream=True,
                    stream_options={"include_usage": True},
                    **self.client_kwargs,
                )
                contents = [""] * n_out
                reasonings = [""] * n_out
                stream_usage = None
                for chunk in stream:
                    if getattr(chunk, "usage", None):
                        stream_usage = chunk.usage
                    if not chunk.choices:
                        continue
                    for c in chunk.choices:
                        idx = getattr(c, "index", 0) or 0
                        if idx >= n_out:
                            continue
                        delta = c.delta
                        if delta is None:
                            continue
                        piece = getattr(delta, "content", None)
                        if piece:
                            contents[idx] += piece
                        r_piece = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                        if r_piece:
                            reasonings[idx] += r_piece
                results = []
                for i in range(n_out):
                    content = contents[i]
                    if not content and reasonings[i]:
                        content = reasonings[i]
                    results.append(content)
                # think 文本单独传入避免把 reasoning 算进 prediction
                self._record_token_usage(stream_usage, contents, reasonings, sample_id=task_id)
                return results
            response = OpenAIRunner.client.chat.completions.create(
                messages=prompt,
                **self.client_kwargs,
            )
        except (
            openai.APIError,
            openai.RateLimitError,
            openai.InternalServerError,
            openai.OpenAIError,
            openai.APIStatusError,
            openai.APITimeoutError,
            openai.InternalServerError,
            openai.APIConnectionError,
        ) as e:
            print("Exception: ", repr(e))
            print("Sleeping for 30 seconds...")
            print("Consider reducing the number of parallel processes.")
            sleep(30)
            return self._run_single(prompt, n=n - 1, task_id=task_id)
        except Exception as e:
            print(f"Failed to run the model for {prompt}!")
            print("Exception: ", repr(e))
            raise e
        results = []
        contents = []
        reasonings = []
        for c in response.choices:
            content = c.message.content or ""
            reasoning = ""
            if hasattr(c.message, "reasoning_content") and c.message.reasoning_content:
                reasoning = c.message.reasoning_content
            elif hasattr(c.message, "reasoning") and c.message.reasoning:
                reasoning = c.message.reasoning
            contents.append(content)
            reasonings.append(reasoning)
            # 返回值沿用原逻辑：content 为空则回退 reasoning
            results.append(content if content else reasoning)
        self._record_token_usage(getattr(response, "usage", None), contents, reasonings, sample_id=task_id)
        return results

    def _record_token_usage(self, usage, contents, reasonings=None, sample_id=None):
        """逐条记录本次请求的 token 用量与 error/empty 标志。

        contents / reasonings 分别为各 choice 的答案文本与思考文本，
        think 文本单独传入以避免把 reasoning 算进 prediction。
        sample_id (v2): 本次 API call 的 base sid（如 "codegeneration:3487"），
        每个 choice 会拼上 "#i" 后缀，落盘为 "codegeneration:3487#0" 这种格式，
        跟 code_list/graded_list 的 slot 一一对应，pass@k 场景零偏差。
        """
        try:
            reasonings = reasonings or [None] * len(contents)
            for i, text in enumerate(contents):
                reasoning_text = reasonings[i] if i < len(reasonings) else None
                # usage 为整次请求总量，仅记到第一个 choice，其余记 None 避免重复计数
                input_tokens, prediction_tokens, think_tokens = compute_tokens(
                    usage if i == 0 else None,
                    text=text,
                    reasoning_text=reasoning_text or None,
                )
                stripped = (text or "").strip()
                is_empty = stripped == ""
                is_error = stripped.upper().startswith("ERROR")
                # per-choice sid：n>1 时 #0/#1/... 各占一条；base sid 为 None 时保持 legacy 无 sid
                per_choice_sid = f"{sample_id}#{i}" if sample_id else None
                append_token_record(
                    input_tokens=input_tokens,
                    prediction_tokens=prediction_tokens,
                    think_tokens=think_tokens,
                    is_error=is_error,
                    is_empty=is_empty,
                    sample_id=per_choice_sid,
                )
        except Exception:
            pass
