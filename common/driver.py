import numpy as np
import tensorflow as tf

class Driver:

  def __init__(self, envs, **kwargs):
    self._envs = envs
    self._kwargs = kwargs
    self._on_steps = []
    self._on_resets = []
    self._on_episodes = []
    self._act_spaces = [env.act_space for env in envs]
    self.reset()

  def on_step(self, callback):
    self._on_steps.append(callback)

  def on_reset(self, callback):
    self._on_resets.append(callback)

  def on_episode(self, callback):
    self._on_episodes.append(callback)

  def reset(self):
    self._obs = [None] * len(self._envs)
    self._eps = [None] * len(self._envs)
    self._state = None

  def __call__(self, policy, steps=0, loop=0, log_x_out=False, episodes=0, reporting_step=-1):
    step, episode = 0, 0
    x_out_buffer = tf.reshape(tf.convert_to_tensor((), dtype=tf.float16), (0, 400))
    
    while step < steps or episode < episodes:
      obs = {
          i: self._envs[i].reset()
          for i, ob in enumerate(self._obs) if ob is None or ob['is_last']}
      for i, ob in obs.items():
        self._obs[i] = ob() if callable(ob) else ob
        act = {k: np.zeros(v.shape) for k, v in self._act_spaces[i].items()}
        tran = {k: self._convert(v) for k, v in {**ob, **act}.items()}
        [fn(tran, worker=i, **self._kwargs) for fn in self._on_resets]
        self._eps[i] = [tran]
      obs = {k: np.stack([o[k] for o in self._obs]) for k in self._obs[0]}
      
      if log_x_out:
          actions, self._state, x_out = policy(obs, self._state, **self._kwargs)
          x_out_buffer = tf.concat([x_out_buffer, x_out], axis=0)
      else:
          actions, self._state, _ = policy(obs, self._state, **self._kwargs)

      actions = [
          {k: np.array(actions[k][i]) for k in actions}
          for i in range(len(self._envs))]
      assert len(actions) == len(self._envs)
      obs = [e.step(a) for e, a in zip(self._envs, actions)]
      obs = [ob() if callable(ob) else ob for ob in obs]
      for i, (act, ob) in enumerate(zip(actions, obs)):
        tran = {k: self._convert(v) for k, v in {**ob, **act}.items()}
        [fn(tran, worker=i, **self._kwargs) for fn in self._on_steps]
        self._eps[i].append(tran)
        #step += 1
        if ob['is_last']:
          ep = self._eps[i]
          ep = {k: self._convert([t[k] for t in ep]) for k in ep[0]}
          [fn(ep, **self._kwargs) for fn in self._on_episodes]
          print(f"Episode: {episode}, step: {step}") 

          if episode % 4 == 0 and log_x_out:
            score = float(ep['reward'].astype(np.float64).sum())
            np.savez_compressed(f'storage/my_logs/x_out_L_{loop}_E_{episode}', x_out=x_out_buffer.numpy(), episode=episode, loop=loop, reward=score, step=reporting_step+step)


          episode += 1
        step += 1
      self._obs = obs

  def _convert(self, value):
    value = np.array(value)
    if np.issubdtype(value.dtype, np.floating):
      return value.astype(np.float32)
    elif np.issubdtype(value.dtype, np.signedinteger):
      return value.astype(np.int32)
    elif np.issubdtype(value.dtype, np.uint8):
      return value.astype(np.uint8)
    return value
