"""
CatVTON Attention Processors.

Adapted from https://github.com/Zheng-Chong/CatVTON (ICLR 2025).
SkipAttnProcessor skips cross-attention (CatVTON uses no text encoder).
AttnProcessor2_0 uses PyTorch 2.0 scaled dot-product attention with
memory-efficient chunked fallback for MPS/limited VRAM devices.
"""

import math
import torch
from torch.nn import functional as F


def _chunked_attention(query, key, value, attn_mask=None, dropout_p=0.0, chunk_size=4096):
    """
    Memory-efficient attention that processes in chunks.
    Avoids large buffer allocations that cause OOM on MPS and limited VRAM.
    """
    batch_size, num_heads, seq_len, head_dim = query.shape
    
    # Compute attention scores in chunks to limit memory usage
    output = torch.zeros_like(query)
    
    for start_idx in range(0, seq_len, chunk_size):
        end_idx = min(start_idx + chunk_size, seq_len)
        
        # Get chunk of queries
        q_chunk = query[:, :, start_idx:end_idx, :]
        
        # Compute attention scores for this chunk: (batch, heads, chunk, seq)
        scores = torch.matmul(q_chunk, key.transpose(-2, -1)) / math.sqrt(head_dim)
        
        # Apply attention mask if provided
        if attn_mask is not None:
            scores = scores + attn_mask[:, :, start_idx:end_idx, :]
        
        # Softmax and dropout
        attn_weights = F.softmax(scores, dim=-1)
        if dropout_p > 0.0:
            attn_weights = F.dropout(attn_weights, p=dropout_p, training=True)
        
        # Apply to values
        output[:, :, start_idx:end_idx, :] = torch.matmul(attn_weights, value)
    
    return output


class SkipAttnProcessor(torch.nn.Module):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def __call__(self, attn, hidden_states, encoder_hidden_states=None,
                 attention_mask=None, temb=None):
        return hidden_states


class AttnProcessor2_0(torch.nn.Module):
    def __init__(self, hidden_size=None, cross_attention_dim=None, **kwargs):
        super().__init__()
        if not hasattr(F, "scaled_dot_product_attention"):
            raise ImportError("AttnProcessor2_0 requires PyTorch 2.0+")
        # Default chunk size for memory-efficient attention fallback
        self.chunk_size = kwargs.get("chunk_size", 2048)

    def __call__(self, attn, hidden_states, encoder_hidden_states=None,
                 attention_mask=None, temb=None, *args, **kwargs):
        residual = hidden_states
        if attn.spatial_norm is not None:
            hidden_states = attn.spatial_norm(hidden_states, temb)

        input_ndim = hidden_states.ndim
        if input_ndim == 4:
            batch_size, channel, height, width = hidden_states.shape
            hidden_states = hidden_states.view(batch_size, channel, height * width).transpose(1, 2)

        batch_size, sequence_length, _ = (
            hidden_states.shape if encoder_hidden_states is None
            else encoder_hidden_states.shape
        )
        if attention_mask is not None:
            attention_mask = attn.prepare_attention_mask(attention_mask, sequence_length, batch_size)
            attention_mask = attention_mask.view(batch_size, attn.heads, -1, attention_mask.shape[-1])

        if attn.group_norm is not None:
            hidden_states = attn.group_norm(hidden_states.transpose(1, 2)).transpose(1, 2)

        query = attn.to_q(hidden_states)
        if encoder_hidden_states is None:
            encoder_hidden_states = hidden_states
        elif attn.norm_cross:
            encoder_hidden_states = attn.norm_encoder_hidden_states(encoder_hidden_states)

        key = attn.to_k(encoder_hidden_states)
        value = attn.to_v(encoder_hidden_states)

        inner_dim = key.shape[-1]
        head_dim = inner_dim // attn.heads

        query = query.view(batch_size, -1, attn.heads, head_dim).transpose(1, 2)
        key = key.view(batch_size, -1, attn.heads, head_dim).transpose(1, 2)
        value = value.view(batch_size, -1, attn.heads, head_dim).transpose(1, 2)

        # Try efficient SDPA first, fallback to chunked attention on memory errors
        # MPS devices often fail with large buffer allocations
        try:
            # Check if this would require a huge buffer on MPS
            if query.device.type == "mps":
                seq_len = query.shape[2]
                # Rough heuristic: MPS struggles with attention buffers > ~4GB
                # Each attention matrix is (batch * heads * seq * seq) floats
                estimated_bytes = batch_size * attn.heads * seq_len * seq_len * 4
                if estimated_bytes > 4 * 1024**3:  # > 4GB
                    raise RuntimeError("MPS memory limit exceeded, using chunked fallback")
            
            hidden_states = F.scaled_dot_product_attention(
                query, key, value, attn_mask=attention_mask, dropout_p=0.0, is_causal=False
            )
        except RuntimeError as e:
            if "buffer size" in str(e).lower() or "memory" in str(e).lower() or "MPS" in str(e):
                # Use memory-efficient chunked attention
                hidden_states = _chunked_attention(
                    query, key, value, attn_mask=attention_mask, dropout_p=0.0, 
                    chunk_size=self.chunk_size
                )
            else:
                raise
        
        hidden_states = hidden_states.transpose(1, 2).reshape(batch_size, -1, attn.heads * head_dim)
        hidden_states = hidden_states.to(query.dtype)

        hidden_states = attn.to_out[0](hidden_states)
        hidden_states = attn.to_out[1](hidden_states)

        if input_ndim == 4:
            hidden_states = hidden_states.transpose(-1, -2).reshape(batch_size, channel, height, width)
        if attn.residual_connection:
            hidden_states = hidden_states + residual
        hidden_states = hidden_states / attn.rescale_output_factor
        return hidden_states
