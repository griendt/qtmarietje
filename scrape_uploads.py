import re

f = open("PHPMarietje.html",'r')
data = f.read()
f.close()

pos = data.find("class=\"forum2\"")
stripped = data[pos:]
pos2 = stripped.find("</table>")
stripped = stripped[:pos2]

r = re.compile("<tr class=\"forum1\">(.*?)</tr>",re.I | re.S)

lines = []
for m in r.findall(stripped):
    lines.append(m[4:-5])

parsed = []
index = {}

for d in lines:
    pos = d.find("id=")
    pos2 = d.find("&")
    i = int(d[pos+3:pos2])
    d = d[pos2:]
    pos = d.find(">")
    pos2 = d.find("</td>")
    artist = d[pos+1:pos2]
    d = d[pos2+15:]
    pos = d.find(">")
    pos2 = d.find("</td>")
    title = d[pos+1:pos2]
    #print(repr(d))
    if d=="": continue
    uploader = d.splitlines()[-1]
    parsed.append((artist,title,i,uploader))
    index[i] = uploader

s = "\n".join(["%d: %s" % (k,v) for k,v in sorted(index.items(),key=lambda x:x[0])])
f = open("uploader_info.txt",'w')
f.write(s)
f.close()
