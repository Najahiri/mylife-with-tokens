"""Load text and Apertus 1.5 multimodal backbones using the appropriate HF class."""


def load_backbone(model_id, quantization_config, gpu_id):
    import transformers

    try:
        config = transformers.AutoConfig.from_pretrained(model_id, trust_remote_code=True)
    except ValueError as error:
        raise RuntimeError(
            "The installed Transformers cannot load this model configuration. "
            "For Apertus 1.5, install training/requirements-hf.txt (Swiss AI's pinned fork)."
        ) from error
    if config.model_type == "apertus1p5":
        loader = getattr(transformers, "AutoModelForMultimodalLM", None)
        if loader is None:
            raise RuntimeError("Apertus 1.5 needs Swiss AI's Transformers fork; install training/requirements-hf.txt")
    else:
        loader = transformers.AutoModelForCausalLM
    return loader.from_pretrained(
        model_id, config=config, quantization_config=quantization_config,
        device_map={"": gpu_id}, trust_remote_code=True,
    )
