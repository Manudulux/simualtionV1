import streamlit as st
import simpy
import random
import time
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURATION & COORDINATES ---
# Layout constants for the 2D Map
MACHINE_POS = (0, 5)
GANTRY_POS = (2, 5)
FINISHING_POS = (15, 5)
CAVITY_COLS = 8
CAVITY_ROWS = 3

# Generate coordinates for 24 cavities in a grid (x: 5 to 12, y: 3 to 7)
CAVITY_POSITIONS = []
for r in range(CAVITY_ROWS):
    for c in range(CAVITY_COLS):
        CAVITY_POSITIONS.append((5 + c, 3 + r * 2))

class Tire:
    def __init__(self, id):
        self.id = id
        self.pos = MACHINE_POS
        self.color = "limegreen" # Green tire
        self.status = "Building"

# --- SIMULATION ENGINE ---
class FactoryEnv:
    def __init__(self, env, num_cavities, build_time, cure_time):
        self.env = env
        self.num_cavities = num_cavities
        self.build_time = build_time # e.g., 30s
        self.cure_time = cure_time   # e.g., 720s (12m)
        self.cavities = simpy.Resource(env, num_cavities)
        self.active_tires = []
        self.total_finished = 0
        self.gantry_queue = []

    def build_tire_process(self):
        tire_count = 1
        while True:
            # Machine builds a green tire: 30 +/- 3 seconds
            yield self.env.timeout(random.uniform(self.build_time - 3, self.build_time + 3))
            new_tire = Tire(f"T{tire_count}")
            self.active_tires.append(new_tire)
            self.env.process(self.tire_lifecycle(new_tire))
            tire_count += 1

    def tire_lifecycle(self, tire):
        # 1. Enter Gantry
        tire.status = "In Gantry"
        # Visual stacking in gantry
        tire.pos = (GANTRY_POS[0], GANTRY_POS[1] + (len(self.gantry_queue) * 0.2))
        self.gantry_queue.append(tire)

        # 2. Request Curing Cavity
        with self.cavities.request() as req:
            yield req
            self.gantry_queue.remove(tire)
            
            # Find an available cavity coordinate
            # (Simple logic: pick the first one not occupied)
            occupied_positions = [t.pos for t in self.active_tires if t.status == "Curing"]
            available_pos = next(p for p in CAVITY_POSITIONS if p not in occupied_positions)
            
            # 3. Curing Process (Turn into black tire)
            tire.status = "Curing"
            tire.pos = available_pos
            # 12 minutes +/- variance (using 60s variance)
            yield self.env.timeout(random.uniform(self.cure_time - 60, self.cure_time + 60))
            
            # 4. Finish / Inspection
            tire.color = "black"
            tire.status = "Finished"
            tire.pos = FINISHING_POS
            yield self.env.timeout(20) # Brief stay in finishing
            
            self.total_finished += 1
            self.active_tires.remove(tire)

# --- STREAMLIT UI SETUP ---
st.set_page_config(page_title="Tire Factory Digital Twin", layout="wide")

if 'running' not in st.session_state:
    st.session_state.running = False

st.title("🏭 Tire Factory Digital Twin")
st.markdown("Real-time simulation of Green Tire building, Gantry storage, and Curing.")

# Sidebar for parameters
with st.sidebar:
    st.header("Simulation Settings")
    build_t = st.number_input("Build Time (sec)", value=30)
    cure_t_min = st.number_input("Cure Time (min)", value=12)
    sim_speed = st.slider("Warp Speed (Sim-sec per Update)", 1, 100, 30)
    
    if not st.session_state.running:
        if st.button("🚀 Start Production", use_container_width=True):
            st.session_state.running = True
            st.rerun()
    else:
        if st.button("🛑 Stop Production", use_container_width=True):
            st.session_state.running = False
            st.rerun()

# Placeholders for Dashboard
m_col1, m_col2, m_col3 = st.columns(3)
kpi1 = m_col1.empty()
kpi2 = m_col2.empty()
kpi3 = m_col3.empty()

plot_spot = st.empty()

# --- RUN SIMULATION ---
if st.session_state.running:
    # Initialize SimPy Environment
    sim_env = simpy.Environment()
    factory = FactoryEnv(sim_env, 24, build_t, cure_t_min * 60)
    sim_env.process(factory.build_tire_process())

    # Animation Loop
    while st.session_state.running:
        # Step the simulation forward
        sim_env.run(until=sim_env.now + sim_speed)

        # Update Metrics
        kpi1.metric("Gantry Inventory", len(factory.gantry_queue))
        kpi2.metric("Tires Finished", factory.total_finished)
        utilization = (factory.cavities.count / 24) * 100
        kpi3.metric("Cavity Utilization", f"{utilization:.1f}%")

        # Prepare Map Data
        fig = go.Figure()

        # Add Factory Background Annotations
        fig.add_annotation(x=MACHINE_POS[0], y=MACHINE_POS[1]+1, text="Building Machine", showarrow=False)
        fig.add_annotation(x=GANTRY_POS[0], y=GANTRY_POS[1]+3, text="Gantry", showarrow=False)
        fig.add_annotation(x=8.5, y=8, text="Curing Cavities (n=24)", showarrow=False)
        fig.add_annotation(x=FINISHING_POS[0], y=FINISHING_POS[1]+1, text="Finishing Area", showarrow=False)

        # Draw Tires
        if factory.active_tires:
            df = pd.DataFrame([{
                'x': t.pos[0], 'y': t.pos[1], 
                'color': t.color, 'id': t.id, 'status': t.status
            } for t in factory.active_tires])

            fig.add_trace(go.Scatter(
                x=df['x'], y=df['y'],
                mode='markers+text',
                marker=dict(size=22, color=df['color'], line=dict(width=1.5, color='white')),
                text=df['id'] if len(df) < 50 else None, # Hide text if too crowded
                textposition="top center",
                customdata=df['status'],
                hovertemplate="<b>%{text}</b><br>Status: %{customdata}<extra></extra>"
            ))

        # Map Layout settings
        fig.update_layout(
            xaxis=dict(range=[-2, 18], showgrid=False, zeroline=False, visible=False),
            yaxis=dict(range=[-1, 10], showgrid=False, zeroline=False, visible=False),
            height=500,
            margin=dict(l=10, r=10, t=10, b=10),
            template="plotly_dark",
            showlegend=False
        )

        # RENDER: Use a unique key to prevent DuplicateElementId error
        plot_spot.plotly_chart(fig, use_container_width=True, key="factory_map_main")
        
        # Small sleep to let Streamlit's web-socket breathe
        time.sleep(0.05)
else:
    st.info("Click 'Start Production' in the sidebar to begin the simulation.")
