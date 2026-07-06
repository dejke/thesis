import docker

targets = ["target", "database"] 


client = docker.from_env()
attacker = client.containers.get("attacker")


result = attacker.exec_run(f"curl http://target:8080/secret.txt")
print(result.output.decode())
