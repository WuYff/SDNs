from collections import defaultdict

a = defaultdict(dict)
a[1][2] = 1
a[1][7] = 8
a[3][4] = 5
for i in a:
    print(i)
    for j in a[i]:
        print("qqqqq  {} ".format(j))


