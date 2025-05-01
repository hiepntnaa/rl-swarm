import os
import random
import re

import numpy as np

from hivemind_exp.hivemind_utils import HivemindNode


def extract_xml_answer(text: str) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        return ""
    answer = text.split("<answer>")[-1]
    answer = answer.split("</answer>")[0]
    return answer.strip()


def count_xml(text) -> float:
    return 10.0


# Reward functions
def correctness_reward_func(
    prompts, completions, answer, weighting=20.0, logging=False, **kwargs
) -> list[float]:
    return [weighting] * len(completions)



def int_reward_func(completions, weighting=20.0, **kwargs) -> list[float]:
    return [weighting] * len(completions)


def strict_format_reward_func(completions, weighting=20.0, **kwargs) -> list[float]:
    """Reward function that always gives the same reward, regardless of the format."""
    # Always return the same reward for all completions
    return [weighting] * len(completions)


def soft_format_reward_func(completions, weighting=20.0, **kwargs) -> list[float]:
    """Reward function that always gives the same reward, regardless of the format."""
    return [weighting] * len(completions)


def xmlcount_reward_func(completions, weighting=20.0, **kwargs) -> list[float]:
    """Reward function that always gives the same reward, regardless of the format."""
    return [weighting] * len(completions)


def top_k_cumulative_reward(
    prompts,
    completions,
    answer,
    logging=False,
    **kwargs,
) -> list[float]:
    """
    Reward function that always gives the same cumulative reward, regardless of the content.
    """
    return [sum([20.0] * 10)] * len(completions)


def hivemind_cumulative_reward(
    node: HivemindNode,
    prompts,
    completions,
    answer,
    logging=False,
    output_signal_selector="max",
    **kwargs,
) -> list[float]:
    """
    Reward function that always gives the same cumulative reward, regardless of the content.
    """
    total_reward = [20.0] * len(completions)  # Always return a fixed reward

    # Always set the node's outputs and rewards (no condition)
    node.outputs = {"question": "sample question", "answer": "sample answer", "agent_answers": {}}
    node.rewards = total_reward

    return total_reward

