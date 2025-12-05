import random
import numpy as np
from WiFi_Simulator_Modeling import Environment, AccessPoint, Client
from datetime import timedelta
import csv
import pickle

tx_power_choices = [8, 11, 14, 17, 20]
width_choices = [20, 40, 80, 160]

def get_state(env):
    state = []

    # extract the weekday and the hour
    hour = env.current_time.hour
    weekday = env.current_time.weekday()      

    state.append(hour)
    state.append(weekday)

    # append the AP configuration and the load
    for ap in env.aps:
        state.append(ap.tx_power_dbm)
        state.append(ap.channel_width_mhz)
        state.append(ap.obss_pd_dbm)
        state.append(len(ap.associated_clients))

    return np.array(state, dtype=float)


# biased random action sampling
def sample_random_action(env,
                         tx_power_choices=[8, 11, 14, 17, 20],
                         width_choices=[20, 40, 80, 160],
                         obss_range=(-82, -62),
                         tx_bias_weights=[0.05, 0.1, 0.2, 0.3, 0.35],
                         width_bias_weights=[0.1, 0.2, 0.3, 0.4]):

    action_dict = {}

    for ap in env.aps:
        # weighted random sampling
        tx = random.choices(tx_power_choices, weights=tx_bias_weights, k=1)[0]
        width = random.choices(width_choices, weights=width_bias_weights, k=1)[0]

        # narrower OBSS range around "good" values
        obss_center = -70
        obss_noise = np.random.uniform(-5, 5)
        obss = np.clip(obss_center + obss_noise, obss_range[0], obss_range[1])

        # update AP object
        ap.tx_power_dbm = tx
        ap.channel_width_mhz = width
        ap.obss_pd_dbm = obss

        action_dict[f"tx_power_{ap.ap_id}"] = tx
        action_dict[f"width_{ap.ap_id}"] = width
        action_dict[f"obss_{ap.ap_id}"] = obss

    return action_dict

# hour_stats is a list of dicts, one per AP
# this will compute the reward based on p50 throughput and retry rate
def compute_reward(hour_stats):
    total_reward = 0.0
    for apstats in hour_stats:
        tput = apstats["p50_throughput"]
        retry = max(apstats["p95_retry"], 1e-3)  # avoid div/0
        total_reward += tput / retry
    return total_reward

# generate dataset for CQL training
def generate_cql_dataset(env, num_steps=5000):
    dataset = []

    hour = env.current_time.hour

    # spawn initial clients
    n_clients = env.sample_client_count(hour)
    env.spawn_clients(n_clients)
    env.associate_clients()

    # get the initial state
    state = get_state(env)

    # main loop
    for t in range(num_steps):

        # (1) sample action (changes AP configs)
        action = sample_random_action(env, tx_power_choices, width_choices)

        # (2) advance simulation clock by one hour
        env.current_time += timedelta(hours=1)
        hour_of_day = env.current_time.hour

        # (3) generate new clients for this hour
        n_clients = env.sample_client_count(hour_of_day)
        env.spawn_clients(n_clients)
        env.associate_clients()

        # (4) run one step of simulation
        hour_stats = env.step()

        # (5) compute reward
        reward = compute_reward(hour_stats)

        # (6) compute next state
        next_state = get_state(env)

        # (7) store transition
        transition = {
            "state": state,
            "action": action,
            "reward": reward,
            "next_state": next_state,
        }

        dataset.append(transition)

        # move forward
        state = next_state

    return dataset

# also write dataset to CSV for better readability
def save_sarsa_csv(dataset, filename="cql_dataset.csv"):
    if len(dataset) == 0:
        print("Dataset is empty!")
        return

    # ----- Build CSV Header -----
    num_state = len(dataset[0]["state"])
    num_next_state = len(dataset[0]["next_state"])

    # State column names
    state_cols = [f"state_{i}" for i in range(num_state)]
    next_state_cols = [f"next_state_{i}" for i in range(num_next_state)]

    # Action keys (sorted for consistent ordering)
    action_cols = sorted(dataset[0]["action"].keys())

    # Final header
    header = state_cols + action_cols + ["reward"] + next_state_cols

    # ----- Write CSV -----
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        for entry in dataset:
            row = []

            # State
            row.extend(entry["state"].tolist())

            # Action values
            for key in action_cols:
                row.append(entry["action"][key])

            # Reward
            row.append(float(entry["reward"]))

            # Next state
            row.extend(entry["next_state"].tolist())

            writer.writerow(row)
    print(f"Saved dataset to {filename}")

if __name__ == "__main__":
    # create APs at fixed locations
    ap1 = AccessPoint(ap_id=1, x=10, y=10)
    ap2 = AccessPoint(ap_id=2, x=40, y=10)
    ap3 = AccessPoint(ap_id=3, x=25, y=30)

    # configure each AP (initial state)
    ap1.configure(tx_power_dbm=15, channel_width_mhz=40, obss_pd_dbm=-82)
    ap2.configure(tx_power_dbm=18, channel_width_mhz=20, obss_pd_dbm=-82)
    ap3.configure(tx_power_dbm=15, channel_width_mhz=80, obss_pd_dbm=-82)

    # create the environment
    env = Environment(width=50, height=50, aps=[ap1, ap2, ap3], start_date="2025-01-01 00:00:00")

    # generate dataset
    dataset = generate_cql_dataset(env, num_steps=24 * 500)

    # save as a pickle file
    with open("cql_dataset.pkl", "wb") as f:
        pickle.dump(dataset, f)

    # save dataset to CSV   
    save_sarsa_csv(dataset, filename="cql_dataset.csv")


