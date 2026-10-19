from typing import Tuple, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

# ==============================================================================
# POINTER HEAD MODULE
# ==============================================================================

class PointerHead(nn.Module):
    """
    Kev-style pointer head. Projects option representations and question decision 
    representation into a low-dimensional subspace (dp=256) and computes dot-product scores.
    """
    def __init__(self, d_model: int, dp: int = 256):
        super().__init__()
        self.d_model = d_model
        self.dp = dp
        self.q = nn.Linear(d_model, dp, bias=False)
        self.k = nn.Linear(d_model, dp, bias=False)
        self.scale = dp ** -0.5
        # Calibrated temperature parameter (inference only)
        self.register_buffer("temperature", torch.tensor(1.0, dtype=torch.float32))

    def forward(
        self, 
        h_decide: torch.Tensor, 
        h_opts: torch.Tensor, 
        mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Args:
            h_decide: [B, d_model] - Hidden state of the decision token
            h_opts:   [B, K, d_model] - Hidden states of the K options
            mask:     [B, K] - Bool tensor where True indicates valid option
        Returns:
            logits:   [B, K] - Unnormalized scores for each option
        """
        B, K, D = h_opts.shape
        q_proj = self.q(h_decide).unsqueeze(1)  # [B, 1, dp]
        k_proj = self.k(h_opts)                 # [B, K, dp]
        
        # Batched dot product: [B, K]
        logits = (q_proj * k_proj).sum(dim=-1) * self.scale
        
        if mask is not None:
            logits = logits.masked_fill(~mask, -1e9)
            
        if not self.training and self.temperature.item() != 1.0:
            logits = logits / self.temperature
            
        return logits


# ==============================================================================
# FULL ARCHITECTURE
# ==============================================================================

class ApertusDecisionModel(nn.Module):
    def __init__(self, backbone: nn.Module, d_model: int, dp: int = 256):
        super().__init__()
        self.backbone = backbone
        self.pointer_head = PointerHead(d_model=d_model, dp=dp)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        decide_indices: torch.Tensor,
        opt_indices: torch.Tensor,
        opt_mask: torch.Tensor,
        labels: Optional[torch.Tensor] = None,
    ) -> Tuple[Optional[torch.Tensor], torch.Tensor]:
        """
        Args:
            input_ids:      [B, SeqLen]
            attention_mask: [B, SeqLen]
            decide_indices: [B] - Position index of the [DECIDE] token
            opt_indices:    [B, K] - Position indices of closing [/OPTION] tokens
            opt_mask:       [B, K] - True if option exists (handles variable choices)
            labels:         [B] - Target option index (0 to K-1)
        """
        outputs = self.backbone(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
            return_dict=True,
        )
        
        # Last layer hidden states: [B, SeqLen, D]
        last_hidden = outputs.hidden_states[-1]
        B, SeqLen, D = last_hidden.shape

        # Extract h_decide: [B, D]
        batch_idx = torch.arange(B, device=input_ids.device)
        h_decide = last_hidden[batch_idx, decide_indices]

        # Extract h_opts: [B, K, D]
        K = opt_indices.shape[1]
        expanded_batch = batch_idx.unsqueeze(1).expand(B, K)
        
        # Clamp padded indices to 0 for safe gathering; masked out later
        safe_opt_indices = opt_indices.clamp(min=0, max=SeqLen - 1)
        h_opts = last_hidden[expanded_batch, safe_opt_indices]

        logits = self.pointer_head(h_decide, h_opts, mask=opt_mask)

        loss = None
        if labels is not None:
            loss = F.cross_entropy(logits, labels)

        return loss, logits
