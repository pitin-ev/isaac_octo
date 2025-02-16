import argparse

from omni.isaac.lab.app import AppLauncher

parser = argparse.ArgumentParser(description="Keyboard teleoperation for Isaac Lab environments.")
parser.add_argument("--task", type=str, default="Isaac-AGV-Managed", help="Name of the task.")
parser.add_argument(
    "--disable_fabric", action="store_true", default=False, help="Disable fabric and use USD I/O operations."
)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(headless=args_cli.headless, enable_cameras=True)
simulation_app = app_launcher.app


import gymnasium as gym
import torch

import carb

from util.se3_keyboard_agv import Se3KeyboardAGV
from omni.isaac.lab.managers import TerminationTermCfg as DoneTerm

import omni.isaac.lab_tasks  # noqa: F401
from omni.isaac.lab_tasks.manager_based.manipulation.lift import mdp
from omni.isaac.lab_tasks.utils import parse_env_cfg
from skrl.memories.torch import RandomMemory
from skrl.utils.spaces.torch import flatten_tensorized_space


def main():
    env_cfg = parse_env_cfg(
        args_cli.task,
        device=args_cli.device,
        num_envs=1,
        use_fabric=not args_cli.disable_fabric,
    )
    env_cfg.terminations.time_out = None
    env = gym.make(args_cli.task, cfg=env_cfg)

    memory = RandomMemory(memory_size=2048, num_envs=1, device=args_cli.device)
    memory.create_tensor(name="states", size=env.observation_space, dtype=torch.float32)
    memory.create_tensor(name="actions", size=env.action_space, dtype=torch.float32)
    memory.create_tensor(name="rewards", size=1, dtype=torch.float32)
    memory.create_tensor(name="terminated", size=1, dtype=torch.bool)
    memory.create_tensor(name="log_prob", size=1, dtype=torch.float32)
    memory.create_tensor(name="values", size=1, dtype=torch.float32)
    memory.create_tensor(name="returns", size=1, dtype=torch.float32)
    memory.create_tensor(name="advantages", size=1, dtype=torch.float32)


    teleop_interface = Se3KeyboardAGV()
    teleop_interface.add_callback("L", env.reset)
    print(teleop_interface)

    states, infos = env.reset()
    teleop_interface.reset()

    while simulation_app.is_running():
        with torch.inference_mode():
            delta_pose = teleop_interface.advance()
            delta_pose = delta_pose.astype("float32")
            delta_pose = torch.tensor(delta_pose, device=env.unwrapped.device).repeat(env.unwrapped.num_envs, 1)
            actions = delta_pose * 20
            next_states, rewards, terminated, truncated, infos = env.step(actions)

            memory.add_samples(
                states=flatten_tensorized_space(states),
                actions=actions,
                rewards=rewards,
                next_states=next_states,
                terminated=terminated,
                truncated=truncated,
                log_prob=torch.zeros_like(rewards),
                values=torch.zeros_like(rewards),
            )

            if terminated.any() or truncated.any():
                states, infos = env.reset()
            else:
                states = next_states

    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
