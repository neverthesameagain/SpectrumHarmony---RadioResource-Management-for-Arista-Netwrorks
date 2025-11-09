# The script finds objects by their Collection. You must organize your scene as follows:
# APs: A collection for all your Access Points.
# Clients: A collection for all your mobile clients (phones, laptops).
# Obstacles: A collection for static obstacles (walls, furniture).
# Interferers: A collection for any interference sources (e.g., a microwave).


# Select an object and go to the Object Properties tab (the orange square icon) and scroll down 
# to Custom Properties. Click New to add the parameters ns-3 will need.
# For AP objects, add:
# ssid (Type: String, Value: e.g., MyWifiNetwork)
# channel (Type: Integer, Value: e.g., 6)
# channel_width_mhz (Type: Integer, Value: e.g., 20)
# For Client objects, add:
# ssid (Type: String, Value: e.g., MyWifiNetwork)
# For Obstacle objects, add:
# loss_db (Type: Float, Value: e.g., 5.0)
# Important: Before running the script, select all your obstacle objects, press Ctrl+A, and choose Apply > Rotation.
# This sets their rotation to zero, which makes the dimensions property accurate for ns-3.
# For Interferer objects, add
# power_dbm (Type: Float, Value: e.g., -30.0)
# frequency_mhz (Type: Integer, Value: e.g., 2450)

import bpy #type: ignore
import json
import os

# --- Configuration ---
SIM_TIME_PER_FRAME = 10.0  # Each Blender frame = 10 seconds of simulation time
OUTPUT_FILENAME = "scene.json"

# Collections to export
COLLECTION_NAMES = {
    "aps": "APs",
    "clients": "Clients",
    "obstacles": "Obstacles",
    "interferers": "Interferers"
}
# --- End Configuration ---


def get_custom_prop(obj, prop_name, default_value):
    """
    Safely gets a custom property from an object,
    returning a default if it doesn't exist.
    NOTE: If a property is animated, this will get
    the value AT THE CURRENT SCENE FRAME.
    """
    return obj.get(prop_name, default_value)


def export_scene_for_ns3():
    
    # Get the directory of the current .blend file
    try:
        blend_dir = os.path.dirname(bpy.data.filepath)
        if not blend_dir:
            raise AttributeError
    except AttributeError:
        print("ERROR: Please save your .blend file before running this script.")
        print("The scene.json file will be saved in the same directory.")
        return

    output_path = os.path.join(blend_dir, OUTPUT_FILENAME)
    
    scene = bpy.context.scene
    frame_start = scene.frame_start
    frame_end = scene.frame_end
    
    print(f"Starting export: {frame_start} to {frame_end} frames...")

    # --- Main data dictionary ---
    output_data = {
        "simulation_settings": {
            "start_time_sec": (frame_start - frame_start) * SIM_TIME_PER_FRAME,
            "stop_time_sec": (frame_end - frame_start) * SIM_TIME_PER_FRAME,
            "tick_interval_sec": SIM_TIME_PER_FRAME,
            "total_frames": (frame_end - frame_start) + 1
        },
        "static_obstacles": [],
        "access_points": [],
        "clients": [],
        "interferers": []
    }

    # --- Process Static Obstacles ---
    # (Obstacles are assumed to be static and are only sampled once)
    print("Exporting Obstacles...")
    if COLLECTION_NAMES["obstacles"] in bpy.data.collections:
        obstacle_col = bpy.data.collections[COLLECTION_NAMES["obstacles"]]
        for obj in obstacle_col.objects:
            loc = obj.location
            dims = obj.dimensions
            
            output_data["static_obstacles"].append({
                "name": obj.name,
                "pos": [loc.x, loc.y, loc.z],
                "dims": [dims.x, dims.y, dims.z],
                "loss_db": get_custom_prop(obj, "loss_db", 3.0) # Default 3dB loss
            })

    # --- Process Dynamic Objects (APs, Clients, Interferers) ---
    dynamic_collections = {
        "access_points": COLLECTION_NAMES["aps"],
        "clients": COLLECTION_NAMES["clients"],
        "interferers": COLLECTION_NAMES["interferers"]
    }

    for data_key, col_name in dynamic_collections.items():
        print(f"Exporting {col_name}...")
        if col_name not in bpy.data.collections:
            print(f"  Warning: Collection '{col_name}' not found. Skipping.")
            continue
            
        collection = bpy.data.collections[col_name]
        
        for obj in collection.objects:
            obj_data = {"name": obj.name}
            
            # Get static custom properties first
            if data_key == "access_points":
                obj_data["ssid"] = get_custom_prop(obj, "ssid", "ns3-default-ssid")
                obj_data["channel"] = get_custom_prop(obj, "channel", 1)
                obj_data["channel_width_mhz"] = get_custom_prop(obj, "channel_width_mhz", 20)
            
            elif data_key == "clients":
                obj_data["ssid"] = get_custom_prop(obj, "ssid", "ns3-default-ssid")
            
            elif data_key == "interferers":
                # Get static properties (power, frequency)
                obj_data["power_dbm"] = get_custom_prop(obj, "power_dbm", -50.0)
                obj_data["frequency_mhz"] = get_custom_prop(obj, "frequency_mhz", 2450)
                # 'on' state is now dynamic and sampled per-frame

            # --- Iterate through timeline for dynamic locations ---
            location_ticks = []
            for frame in range(frame_start, frame_end + 1):
                # Set the scene to the current frame
                scene.frame_set(frame)
                
                # Get the object's final world-space location at this frame
                loc = obj.matrix_world.to_translation()
                
                sim_time = (frame - frame_start) * SIM_TIME_PER_FRAME
                
                # Base data for all dynamic objects
                tick_data = {
                    "time": sim_time,
                    "pos": [loc.x, loc.y, loc.z]
                }
                
                # --- THIS IS THE NEW LOGIC ---
                # If this is an interferer, sample its 'on' property
                if data_key == "interferers":
                    # Get the 'on' property *at this frame* (set the property type to bool)
                    on_state = get_custom_prop(obj, "on", 1)
                    tick_data["on"] = on_state 
                
                location_ticks.append(tick_data)
            
            obj_data["location_ticks"] = location_ticks
            output_data[data_key].append(obj_data)

    # --- Write file and clean up ---
    try:
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=4)
        print(f"\nSUCCESS: Scene exported to {output_path}")
        
    except Exception as e:
        print(f"\nERROR: Could not write file. {e}")

    # Reset frame to the start
    scene.frame_set(frame_start)


# --- Run the function ---
if __name__ == "__main__":
    export_scene_for_ns3()