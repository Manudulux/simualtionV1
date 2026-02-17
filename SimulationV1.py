import streamlit as st
import simpy
import random
import time
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURATION & COORDINATES ---
CAVITY_COLS = 8
CAVITY_ROWS = 3
MACHINE_POS = (0, 5)
GANTRY_POS = (2, 5)
FINISHING_POS = (12, 5)

# Generate coordinates for 24 cavities in a grid (x: 5-10, y: 2-8)
CAVITY_POSITIONS = []
for r in range(CAVITY_ROWS):
    for c in range(CAVITY_COLS):
        CAVITY_POSITIONS.append((5 + c, 2 + r * 3))

class Tire:
    def __init__(self, id):
        self.id = id
        self.pos = MACHINE_POS
        self.color = "limegreen"
        self.status = "Building"

# --- SIMULATION ENGINE ---
class FactoryEnv:
    def __init__(self, env, num_cavities):
        self.env = env
        self.num_cavities = num_cavities
        self.cavities = simpy.Resource(env, num_cavities)
        self.active_tires = []
        self.total_finished = 0
        self.gantry_queue = []

    def build_tire(self):
        tire_count = 0
        while True:
            # Produce a tire every 30 +/- 3 seconds
            yield self.env.timeout(random.uniform(27, 33))
            new_tire = Tire(f"T{tire_count}")
            self.active_tires.append(new_tire)
            self.env.process(self.tire_lifecycle(new_tire))
            tire_count += 1

    def tire_lifecycle(self, tire):
        # 1. Move to Gantry
        tire.status = "In Gantry"
        tire.pos = (GANTRY_POS[0], GANTRY_POS[1] + (len(self.gantry_queue) * 0.2))
        self.gantry_queue.append(tire)

        # 2. Request Cavity
        with self.cavities.request() as req:
            yield req
            self.gantry_queue.remove(tire)
            
            # Find an empty cavity index
            idx = next(i for i in range(self.num_cavities) 
                      if not any(t.pos == CAVITY_POSITIONS[i] for t in self.active_tires if t != tire))
            
            # 3. Curing Process (12m +/- 1m)
            tire.status = "Curing"
            tire.pos = CAVITY_POSITIONS[idx]
            yield self.env.timeout(random.uniform(11*60, 13*60))
            
            # 4. Finish
            tire.color = "black"
            tire.status = "Inspecting"
            tire.pos = FINISHING_POS
            yield self.env.timeout(30) # Inspection time
            
            self.total_finished += 1
            self.active_tires.remove(tire)

# --- STREAMLIT UI ---
st.set_page_config(page_title="Tire Factory Digital Twin", layout="wide")
st.title("🏭 Tire Factory: Real-Time 2D Simulation")

# Sidebar Controls
with st.sidebar:
    st.header("Controls")
    speed = st.select_slider("Simulation Speed", options=[1, 5, 10, 20, 50], value=20)
    run_sim = st.button("Start Production")

# Main Layout
col1, col2 = st.columns([1, 3])
with col1:
    metric_gantry = st.empty()
    metric_finished = st.empty()
    metric_util = st.empty()

with col2:
    plot_spot = st.empty()

if run_sim:
    env = simpy.Environment()
    factory = FactoryEnv(env, 24)
    env.process(factory.build_tire())

    while True:
        # Advance simulation
        env.run(until=env.now + speed)

        # Update Metrics
        metric_gantry.metric("Gantry Stock", len(factory.gantry_queue))
        metric_finished.metric("Total Output", factory.total_finished)
        util = (factory.cavities.count / 24) * 100
        metric_util.metric("Cavity Utilization", f"{util:.1f}%")

        # Create Plotly 2D Map
        fig = go.Figure()

        # Draw Factory Layout (Static elements)
        fig.add_annotation(x=MACHINE_POS[0], y=MACHINE_POS[1]+1, text="Machine", showarrow=False)
        fig.add_annotation(x=GANTRY_POS[0], y=GANTRY_POS[1]+3, text="Gantry", showarrow=False)
        fig.add_annotation(x=7.5, y=10, text="Curing Area (24 Cavities)", showarrow=False)
        fig.add_annotation(x=FINISHING_POS[0], y=FINISHING_POS[1]+1, text="Finishing", showarrow=False)

        # Plot Tires
        if factory.active_tires:
            df = pd.DataFrame([{
                'x': t.pos[0], 'y': t.pos[1], 
                'color': t.color, 'id': t.id, 'status': t.status
            } for t in factory.active_tires])

            fig.add_trace(go.Scatter(
                x=df['x'], y=df['y'],
                mode='markers+text',
                marker=dict(size=20, color=df['color'], line=dict(width=2, color='White')),
                text=df['id'], textposition="top center",
                hovertemplate="<b>%{text}</b><br>Status: %{customdata}",
                customdata=df['status']
            ))

        # Fix Map limits
        fig.update_layout(
            xaxis=dict(range=[-2, 15], showgrid=False, zeroline=False, visible=False),
            yaxis=dict(range=[-1, 12], showgrid=False, zeroline=False, visible=False),
            height=600, margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False,
            template="plotly_dark"
        )

        plot_spot.plotly_chart(fig, use_container_width=True)
        time.sleep(0.05) # UI Throttling
