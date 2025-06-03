a = int(input())
b = int(input())
c = a+b
n = int(input())
total = 0
for i in map(int,input().split()):
    count = i % c
    if count >= a:
        total+= (c - count)
print(total)