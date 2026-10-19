"""Serve the trained adapter and pointer head as an authenticated scoring API."""

from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path
import threading
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Any
    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=1, max_length=64)
    model: str | None = None

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value):
        if not value.strip():
            raise ValueError("question must not be blank")
        return value

    @field_validator("options")
    @classmethod
    def options_not_blank(cls, value):
        if any(not option.strip() for option in value):
            raise ValueError("options must not be blank")
        return value


class DecisionRuntime:
    def __init__(self):
        import torch
        from huggingface_hub import HfApi, snapshot_download
        from peft import PeftConfig, PeftModel
        import transformers
        from training.constants import DELIMITERS
        from training.model import ApertusDecisionModel

        if not torch.cuda.is_available():
            raise RuntimeError("Decision serving requires a CUDA GPU")
        self.model_id = os.environ.get(
            "DECISION_MODEL_ID", "HX-Tfd/Apertus-1.5-8B-Decision"
        )
        revision = os.environ.get("DECISION_REVISION", "main")
        subfolder = os.environ.get("DECISION_SUBFOLDER", "").strip("/")
        if ".." in Path(subfolder).parts:
            raise ValueError("DECISION_SUBFOLDER must stay within the model repository")
        prefix = f"{subfolder}/" if subfolder else ""
        mounted_path = os.environ.get("DECISION_MODEL_PATH")
        if mounted_path:
            if len(revision) != 40 or any(
                c not in "0123456789abcdef" for c in revision
            ):
                raise ValueError(
                    "For mounted weights, set DECISION_REVISION to the mounted Hub commit SHA"
                )
            snapshot = Path(mounted_path)
            self.revision = revision
        else:
            snapshot = Path(
                snapshot_download(
                    self.model_id,
                    revision=revision,
                    allow_patterns=[
                        f"{prefix}{name}"
                        for name in (
                            "adapter_config.json",
                            "adapter_model.safetensors",
                            "adapter_model.bin",
                            "head.pt",
                            "tokenizer*",
                            "special_tokens_map.json",
                            "added_tokens.json",
                            "chat_template*",
                            "vocab.json",
                            "merges.txt",
                            "*.model",
                        )
                    ],
                )
            )
            self.revision = snapshot.name
        self.subfolder = subfolder
        checkpoint = snapshot / subfolder
        adapter_config = PeftConfig.from_pretrained(str(checkpoint))
        self.base_model_id = adapter_config.base_model_name_or_path
        base_revision = (
            os.environ.get("DECISION_BASE_REVISION")
            or adapter_config.revision
            or "main"
        )
        self.base_revision = (
            HfApi().model_info(self.base_model_id, revision=base_revision).sha
        )
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(
            str(checkpoint), trust_remote_code=True
        )
        ids = [
            self.tokenizer.convert_tokens_to_ids(token) for token in DELIMITERS.values()
        ]
        if any(
            value is None or value == self.tokenizer.unk_token_id for value in ids
        ) or len(set(ids)) != len(ids):
            raise ValueError(
                "Checkpoint tokenizer is missing the trained decision delimiter tokens"
            )
        self.device = torch.device("cuda", int(os.environ.get("GPU_ID", "0")))
        self.max_length = int(os.environ.get("DECISION_MAX_LENGTH", "2048"))
        if self.max_length < 1:
            raise ValueError("DECISION_MAX_LENGTH must be positive")
        config = transformers.AutoConfig.from_pretrained(
            self.base_model_id,
            revision=self.base_revision,
            trust_remote_code=True,
        )
        loader = (
            transformers.AutoModelForMultimodalLM
            if config.model_type == "apertus1p5"
            else transformers.AutoModelForCausalLM
        )
        quantization = None
        if os.environ.get("DECISION_4BIT", "true").lower() == "true":
            quantization = transformers.BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
                llm_int8_skip_modules=[
                    "lm_head",
                    "vision_tokenizer",
                    "audio_tokenizer",
                ],
            )
        base = loader.from_pretrained(
            self.base_model_id,
            revision=self.base_revision,
            config=config,
            trust_remote_code=True,
            device_map={"": self.device.index},
            torch_dtype=torch.bfloat16,
            quantization_config=quantization,
        )
        base.resize_token_embeddings(len(self.tokenizer))
        backbone = PeftModel.from_pretrained(base, str(checkpoint), is_trainable=False)
        weights = torch.load(
            checkpoint / "head.pt", map_location="cpu", weights_only=True
        )
        self.model = ApertusDecisionModel(
            backbone,
            d_model=weights["q.weight"].shape[1],
            dp=weights["q.weight"].shape[0],
        )
        self.model.pointer_head.load_state_dict(weights, strict=True)
        self.model.pointer_head.to(self.device, dtype=torch.bfloat16)
        self.model.eval()
        self.lock = threading.Lock()

    def predict(self, request: DecisionRequest) -> dict:
        import torch
        from training.constants import DELIMITERS
        from training.dataset import format_record

        if request.model is not None and request.model != self.model_id:
            raise ValueError(f"This endpoint serves {self.model_id}")
        text = format_record(request.state, request.question, request.options)
        encoded = self.tokenizer(text, truncation=False, return_tensors="pt")
        ids = encoded["input_ids"][0].tolist()
        if len(ids) > self.max_length:
            raise ValueError(
                f"Input has {len(ids)} tokens; maximum is {self.max_length}"
            )
        closes = [
            i
            for i, token in enumerate(ids)
            if token == self.tokenizer.convert_tokens_to_ids(DELIMITERS["opt_close"])
        ]
        decisions = [
            i
            for i, token in enumerate(ids)
            if token == self.tokenizer.convert_tokens_to_ids(DELIMITERS["decide"])
        ]
        if len(closes) != len(request.options) or len(decisions) != 1:
            raise ValueError("Input contains conflicting decision delimiters")
        with (
            self.lock,
            torch.inference_mode(),
            torch.autocast("cuda", dtype=torch.bfloat16),
        ):
            _, logits = self.model(
                input_ids=encoded["input_ids"].to(self.device),
                attention_mask=encoded["attention_mask"].to(self.device),
                decide_indices=torch.tensor(decisions, device=self.device),
                opt_indices=torch.tensor([closes], device=self.device),
                opt_mask=torch.ones(
                    (1, len(closes)), device=self.device, dtype=torch.bool
                ),
            )
            probabilities = logits.float().softmax(-1)[0].cpu().tolist()
        import math

        if not all(math.isfinite(p) for p in probabilities):
            raise RuntimeError("Model returned non-finite decision scores")
        index = max(range(len(probabilities)), key=probabilities.__getitem__)
        return {
            "model": self.model_id,
            "revision": self.revision,
            "subfolder": self.subfolder,
            "base_model": self.base_model_id,
            "base_revision": self.base_revision,
            "prediction_index": index,
            "prediction": request.options[index],
            "probabilities": probabilities,
        }


def create_app(runtime=None, api_key=None, runtime_factory=DecisionRuntime):
    key = api_key if api_key is not None else os.environ.get("DECISION_API_KEY")

    @asynccontextmanager
    async def lifespan(app):
        if not key:
            raise RuntimeError("Set DECISION_API_KEY before starting the server")
        app.state.runtime = runtime if runtime is not None else runtime_factory()
        yield

    app = FastAPI(title="Apertus decision API", lifespan=lifespan)
    bearer = HTTPBearer(auto_error=False)

    def authenticate(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        x_decision_api_key: str | None = Header(default=None),
    ):
        # Keep application authentication separate from a hosting gateway's
        # Authorization header. Bearer remains supported for existing clients.
        supplied_key = (
            x_decision_api_key
            if x_decision_api_key is not None
            else credentials.credentials if credentials else None
        )
        if (
            not key
            or not supplied_key
            or not hmac.compare_digest(supplied_key, key)
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/health")
    def health():
        return {"status": "ready"}

    @app.post("/decide", dependencies=[Depends(authenticate)])
    def decide(request: DecisionRequest):
        try:
            return app.state.runtime.predict(request)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return app


app = create_app()
