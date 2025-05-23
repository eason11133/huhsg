def traingle(a,b,c):
    side = sorted([a,b,c])
    a,b,c = side[0],side[1],side[2]
    if a + b <= c :
        return "No"
    x = a**2
    y = b**2
    z = c**2
    if x + y == z :
        return "Right"
    elif x + y > z :
        return "Acute"
    else :
        return "Obtuse"
a,b,c = map(int,input().split())
print(traingle(a,b,c))