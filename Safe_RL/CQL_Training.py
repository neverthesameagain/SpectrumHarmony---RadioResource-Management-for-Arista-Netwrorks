import random
import copy
import pickle
import numpy as np
from typing import List, Dict
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import os

# tunable hyperparameters
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
BATCH_SIZE = 64
LR = 3e-4
GAMMA = 0.99
TAU = 0.005         
CQL_ALPHA = 1.0     
TRAIN_STEPS = 200000
RANDOM_ACTION_SAMPLES = 16 
NEXT_ACTION_SAMPLES = 16    
PRINT_EVERY = 2000

# action space definitions
tx_power_choices = [8, 11, 14, 17, 20]
width_choices = [20, 40, 80, 160]
obss_min, obss_max = -82.0, -62.0


# the data is converted to a Dataset object for PyTorch
# this allows us to use DataLoader for batching and shuffling
class OfflineWiFiDataset(Dataset):
    def __init__(self, transitions: List[Dict]):
        # preprocess to numpy arrays for speed
        # map each action dict to vector (consistent ordering)
        self.states = []
        self.actions = []
        self.rewards = []
        self.next_states = []

        # determine action ordering by first entry
        if len(transitions) == 0:
            raise ValueError("Empty dataset")

        first_action = transitions[0]["action"]
        # create canonical key order and action_dim via first_action
        self._action_key_order = []
        # infer number of APs if keys like 'tx_power_1' exist
        ap_indices = set()
        for k in first_action.keys():
            parts = k.split('_')
            if len(parts) >= 2 and parts[-1].isdigit():
                ap_indices.add(int(parts[-1]))
        if len(ap_indices) > 0:
            max_ap = max(ap_indices)
            for i in range(1, max_ap+1):
                self._action_key_order.extend([f"tx_power_{i}", f"width_{i}", f"obss_{i}"])
        else:
            self._action_key_order = sorted(first_action.keys())

        for tr in transitions:
            s = np.array(tr["state"], dtype=np.float32)
            ns = np.array(tr["next_state"], dtype=np.float32)
            a = np.array([float(tr["action"][k]) for k in self._action_key_order], dtype=np.float32)
            r = float(tr["reward"])

            self.states.append(s)
            self.actions.append(a)
            self.rewards.append(r)
            self.next_states.append(ns)

        self.states = np.stack(self.states, axis=0)
        self.actions = np.stack(self.actions, axis=0)
        self.rewards = np.array(self.rewards, dtype=np.float32).reshape(-1, 1)
        self.next_states = np.stack(self.next_states, axis=0)

    def __len__(self):
        return self.states.shape[0]

    def __getitem__(self, idx):
        return (
            torch.from_numpy(self.states[idx]).float(),
            torch.from_numpy(self.actions[idx]).float(),
            torch.from_numpy(self.rewards[idx]).float(),
            torch.from_numpy(self.next_states[idx]).float()
        )

# q-network definition
class QNetwork(nn.Module):
    def __init__(self, state_dim: int, action_dim: int, hidden=256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1)
        )

    def forward(self, s: torch.Tensor, a: torch.Tensor) -> torch.Tensor:
        # s: (N, state_dim), a: (N, action_dim)
        x = torch.cat([s, a], dim=-1)
        return self.net(x)

# ----------------------------
# Trainer
# ----------------------------
def train_cql(transitions: List[Dict],
              batch_size=BATCH_SIZE,
              lr=LR,
              gamma=GAMMA,
              tau=TAU,
              cql_alpha=CQL_ALPHA,
              train_steps=TRAIN_STEPS,
              randact_samples=RANDOM_ACTION_SAMPLES,
              nextact_samples=NEXT_ACTION_SAMPLES):
    
    # convert transitions to dataset, creates a PyTorch DataLoader that gives mini-batches
    ds = OfflineWiFiDataset(transitions)
    state_dim = ds.states.shape[1]
    action_dim = ds.actions.shape[1]
    dataloader = DataLoader(ds, batch_size=batch_size, shuffle=True, drop_last=True, pin_memory=True)

    # models and targets
    # two Q-networks are used for CQL
    q1 = QNetwork(state_dim, action_dim).to(DEVICE)
    q2 = QNetwork(state_dim, action_dim).to(DEVICE)
    q1_target = copy.deepcopy(q1).to(DEVICE)
    q2_target = copy.deepcopy(q2).to(DEVICE)
    
    # optimizer for both Q-networks
    optimizer = torch.optim.Adam(list(q1.parameters()) + list(q2.parameters()), lr=lr)

    # helper for sampling random actions per-state (vectorized)
    def sample_random_actions_for_batch(batch_s: torch.Tensor, K: int):
        # batch_s: (B, state_dim)
        B = batch_s.shape[0]
        per_ap = action_dim // 3
        # sample (B, K, action_dim) numpy then convert
        arr = np.zeros((B, K, action_dim), dtype=np.float32)
        for b in range(B):
            for k in range(K):
                vec = []
                for _ in range(per_ap):
                    vec.append(float(random.choice(tx_power_choices)))
                    vec.append(float(random.choice(width_choices)))
                    vec.append(float(random.uniform(obss_min, obss_max)))
                arr[b, k] = np.array(vec, dtype=np.float32)
        return torch.from_numpy(arr).to(DEVICE)  # (B, K, action_dim)

    # training loop
    step = 0
    iterator = iter(dataloader)
    while step < train_steps:
        print("Training step:", step)
        try:
            batch = next(iterator)
        except StopIteration:
            iterator = iter(dataloader)
            batch = next(iterator)
        
        # load batch
        s_batch, a_batch, r_batch, ns_batch = [x.to(DEVICE) for x in batch]

        # compute bellman targets
        # for each ns, approximate max_a' Q_target(ns,a') by sampling nextact_samples
        a_next_samples = sample_random_actions_for_batch(ns_batch, nextact_samples)  # (B,K,ad)
        B = s_batch.shape[0]

        # flatten for network eval
        ns_rep = ns_batch.unsqueeze(1).repeat(1, nextact_samples, 1).reshape(B * nextact_samples, -1)  # (B*K, sd)
        a_next_flat = a_next_samples.reshape(B * nextact_samples, -1)  # (B*K, ad)
        with torch.no_grad():
            q1_next = q1_target(ns_rep, a_next_flat).reshape(B, nextact_samples)  # (B,K)
            q2_next = q2_target(ns_rep, a_next_flat).reshape(B, nextact_samples)
            q_next = torch.min(q1_next, q2_next)  # (B,K)
            # approximate max_a' by taking max over K
            q_next_max, _ = torch.max(q_next, dim=1, keepdim=True)  # (B,1)
            target = r_batch + gamma * q_next_max  # (B,1)

        # current Q estimates
        q1_pred = q1(s_batch, a_batch)  # (B,1)
        q2_pred = q2(s_batch, a_batch)

        # CQL conservative terms
        # sample random actions per state (randact_samples) and compute log-sum-exp
        a_rand = sample_random_actions_for_batch(s_batch, randact_samples)  # (B,K,ad)
        s_rep = s_batch.unsqueeze(1).repeat(1, randact_samples, 1).reshape(B * randact_samples, -1)
        a_rand_flat = a_rand.reshape(B * randact_samples, -1)
        q1_rand_flat = q1(s_rep, a_rand_flat).reshape(B, randact_samples)  # (B,K)
        q2_rand_flat = q2(s_rep, a_rand_flat).reshape(B, randact_samples)
        # logsumexp across K for each state -> (B,)
        logsumexp_q1 = torch.logsumexp(q1_rand_flat, dim=1)  # (B,)
        logsumexp_q2 = torch.logsumexp(q2_rand_flat, dim=1)

        # convert batch-data q values to shape (B,)
        q1_data = q1_pred.view(-1)  # (B,)
        q2_data = q2_pred.view(-1)

        # conservative loss per batch = mean( logsumexp_q - q_data )
        cql1 = cql_alpha * (logsumexp_q1.mean() - q1_data.mean())
        cql2 = cql_alpha * (logsumexp_q2.mean() - q2_data.mean())

        # TD losses 
        loss_q1 = F.mse_loss(q1_pred, target)
        loss_q2 = F.mse_loss(q2_pred, target)

        loss = loss_q1 + loss_q2 + cql1 + cql2

        optimizer.zero_grad()
        loss.backward()
        # gradient clipping optional
        torch.nn.utils.clip_grad_norm_(list(q1.parameters()) + list(q2.parameters()), max_norm=10.0)
        optimizer.step()

        # soft updates
        with torch.no_grad():
            for p, tp in zip(q1.parameters(), q1_target.parameters()):
                tp.data.mul_(1.0 - tau)
                tp.data.add_(tau * p.data)
            for p, tp in zip(q2.parameters(), q2_target.parameters()):
                tp.data.mul_(1.0 - tau)
                tp.data.add_(tau * p.data)

        step += 1

        if step % PRINT_EVERY == 0:
            print(f"[step {step}] loss={loss.item():.4f} td1={loss_q1.item():.4f} td2={loss_q2.item():.4f} cql1={cql1.item():.4f} cql2={cql2.item():.4f}")

    # return trained models and metadata
    return {
        "q1": q1,
        "q2": q2,
        "q1_target": q1_target,
        "q2_target": q2_target,
        "dataset_obj": ds
    }

# the main code
if __name__ == "__main__":
    # path to your dataset pickle file
    dataset_path = "cql_dataset.pkl"

    # try to load dataset either from memory or from disk
    try:
        dataset 
        print("Dataset already loaded in memory.")
    except NameError:
        if os.path.exists(dataset_path):
            with open(dataset_path, "rb") as f:
                dataset = pickle.load(f)
            print(f"Loaded dataset from: {dataset_path}")
        else:
            raise FileNotFoundError(
                f"Dataset not found at: {dataset_path}\n"
                "Please generate the dataset and save it as 'cql_dataset.pkl'."
            )

    print(f"Dataset size: {len(dataset)} transitions")

    # train CQL
    model_info = train_cql(dataset, train_steps=20000)
    
    # get the trained Q-networks
    q1 = model_info["q1"]
    q2 = model_info["q2"]

    # save trained model if desired
    torch.save(q1.state_dict(), "cql_q1.pt")
    torch.save(q2.state_dict(), "cql_q2.pt")


