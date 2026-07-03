import docker

targets = ["target", "database"] 


client = docker.from_env()
attacker = client.containers.get("attacker")
for target in targets:
    print("nmap on ", target)
    result = attacker.exec_run(f"nmap -sV {target}")
    print(result.output.decode())

print(f"fetching target/secret.txt")

result = attacker.exec_run(f"curl http://target:8080/secret.txt")
print(result.output.decode())
