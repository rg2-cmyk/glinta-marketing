#!/bin/bash
cd "/Users/riddhimagoel/Documents/Claude/Projects/Glinta Marketing/dashboard"
exec python3 -m streamlit run app.py --server.port 8506 --server.headless true
