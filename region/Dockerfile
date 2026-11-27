FROM local/claude-workspace-desktop:2
COPY gateway.py profile.py countries.txt /opt/region/
USER developer
ENTRYPOINT ["python3", "-B", "/opt/region/gateway.py"]
