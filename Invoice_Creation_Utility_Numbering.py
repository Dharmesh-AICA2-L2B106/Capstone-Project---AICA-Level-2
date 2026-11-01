"""Invoice creation Utility — Akshay Devpura & Associates.
Run with Python 3.10+ (IDLE: Run > Run Module). First launch installs dependencies.
Manual install: python -m pip install PyQt6 openpyxl Pillow reportlab
Local data: ~/PDF_Studio_Pro_Data. Back up this folder regularly.
GST defaults implement the requested domestic 18% workflow; confirm place of supply.
No IRN generation, GST filing, DSC signing, export/SEZ or reverse-charge workflow.
"""
import sys, os, json, sqlite3, re, shutil, subprocess, importlib.util, base64
import hashlib, hmac, secrets, time, tempfile
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from html import escape

EMBEDDED_CA_LOGO = 'iVBORw0KGgoAAAANSUhEUgAAALMAAACWCAYAAACVdbl2AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAAEnQAABJ0Ad5mH3gAAFhWSURBVHhe7b13nF7Hdd/9PTP33qdsxy56JUE0giBAEuyk2CRSkkXJkmUVx3HkyEVvYvtNcdzyvraVOLFkx7ET27H8WrYVS7JlS4okq1EsYgdJsBcQIDqIXraXp9w7c94/5j67zy5RWAAQpPeHz8XuPmXu3JnfnDlz5pwz4r1XpjGNtwHM1BemMY23KqbJPI23DabJPI23DabJPI23DWR6AXhiiMikv1XPbFOd7fudbqjqK57hbGKazCfB1I55q5HrbKOZzFPbrvH+mcS0mnESqOqkaxrnNqbJfA7h7Tx4zsbzTKsZ03jVeLPViFNhWjJP422DaTJP422DaTJP47TgzVYxOBM6c0OXOhce7q2GqXromW7DZh347YBpyTyNtw2myTyNtw2myXyO4kyrGExRa94O6sZp15nPJE5k5zwbHf92xFQCv9F2nFreVLzR8k+Fack8jbcN/smRWUTGr+PhVO9P481Dc98cr3/eUmpGM0QEhfFLAFQRQMJfaP5v0vfyK3zHT3pvMk7gH9HUhqKNP6Y2rIKCx4CASKgXanL5oSBK/uoJIRrqLxKeBSSvk4R7a4oYmz+hQWXiycMznqL806yqHY9gDZyJ8qeWeUoyTy2A4xTyRnCyBj2VHdRLg5R5J6oi2lym4vGBtt7hvQcRrDH5YAhkbhC+QYUJTJBdCeU3w6gBFcLtAn0aH1ZVMjEYIxhJQ72IQW3O/QzEnJRwog68Bytk6nEY1AuCRT0kVDHGgLF4BMQi6Pgg1bfZxDuVC1P58rrIzHEKer14I2QGh4gDlQmNqfl38TjvA2HEkCnhcpA5R80L2VTh3HS7cY4SCDq1LqIT/J0KESGOhNg6SgnEOflFg2RWCYOs+YZTyyergzFkCKNO6B+pse/QMfoGR0niIotmtjCnp4tSbEgig8ET5isgp/XZxNT6T+3PN4pTlf+6ycxxCns9eK1kbv6MoQ64nBAGxIJYvBp8Tty6c4yMVekfHuVI3zDHBkc4dLSPI8f6ONw/QrXug2QOorf5Vphcgk+gIYUDVH2Q1hqku/qgEhhjMdYwqyPh5usvZ92qJbTFQowEaY7iRTHjakrA1GfFp3gVRjVi054j/OXffYPnXtrD4f4RkqTEeTPL/Mgt1/GeG69mQXeZovgglUXeFKk8tf5T+/NM45wm81RMfd9oHTQFsahEOIlJESopHO0dYM/BY2x/eT/Pv/gSW3bu4cCRAUbqnlQtTgxKNC7FFTBTntX7qWJ7MmxDNGtQVBr1M8ZgrSXOBpnfU+T//fc/zzVrltMWR0Rq0CYyH691G22iLqXqDC8d6Oe//Onf8MimXVSlDEmZeuZpkyq2NsiH3nkVP//x97N0TieJycmsgJxdQr+WvjwTOCWZzzRO1QAijUVPeL/5M6IOVU9dDTWNGKik7D7Uy8ann+fBRzaybX8vo3XIVMiIyCQiJcJhcRhsWDY13W0yBAFp3JdJUhlAtHlan6i/iIAIRakglaPc/o61/Nb//UnmtrUQaSjTS1BT5DjP3Xhmh+HYSMoffP4rfOO+pxjwZWqmhBOLCpj6KC3UKGeDfPLDt/JzH3s/Pa0xFhfKFcMkveltjrckmRt/ZxJRSZXBSsozW3bw/fs2sHHTVg70DqFRgVRKOOIgoUwUSK2Cz7XLSDPMSSwaIhYR8D7c8xVkJmimkGsbzWQGIsmI0z6WzRD+6vf/H1bM6c7JLPiGUWPKIGh+1sHU8uBTm/n13/0ThqSTYV+kbmJUNKhX3hO5Gi2McV5Xwmd+/RdZv3IBRVIi8aiJ/0mR+ezOQ6cRzjn6R2o8s20vn/mTv+RXfue/8+37n2DvkGc0mcGg7aRqW3C2iLMJqYLXIIktjkgzBIfiT3IFyS9GsTbXl6de+S8NadyMurOYpI1K3SMSYZRcoWn6+hQ0CK2q9I7W+PLX/pGqtwxXUjwGUcVoRuTroIo3Ed6WONA3yvfv3cBw1SMmAp+FEfZPCG8qmYW8b/PrFTwh1/0A8KgoNRWGnGX7kRH+5tv382uf+RzfuvdJhnyJimmh4mNqPgp6sRpUQ2lWDJGBWJQYRyKOSJVIIVLFqhKpJ1JHpA6rGcalGJdhvceqJ1JP3HRFqliaLvUYVYz3GPUk1LBZhe72NkpxIa+LAo2FWt4KElQPweF9hgPGnPL4S7t5YttehlNLVCiBKgaHUY9RIbYR1kRkRFSlyF2PPcf2Q/1UMgdGEfG5ySXcR5BctZkw372d8KaqGeNknvTChLxSBecgihSPo6owmFqe2XqQv/7Kt3j42Z0M1xQxFm8saixqDF5yTVgtBsk7TxH1RNaAetQ7otAAaK57K27S6BK1TcMqWCka1RMEMWFTpCFJfUMFyn8WzTDtUcbPfvSDfOLH3ktnoljJwIQaCTbQSkHwGK2Tek9VEw4NjvGv/+CLPPrsDvBFvFpMHKGiQRfWoAJJsDADGSWp88kP3cQvfPgG5kSjSKEMRIANJsvxtna5cJh4vrcDzi0yT4UGUtV9Roahr+K44+Gn+cuvfI8dBwcYo4C3CSIGERM2IWTCvhphsApohsWDq1OMDKXEUkhiukpCezmipaWFcrmEjUyuA4cdOkM0aSPFOTdJr/cKXj3Oebz3VCpjeO/z2URpbS2w/uKVfOi2W5jZElOKgkRWEbzYULeGjFQHPsObiCFn+MEDj/F//9GXqWoZn0UoETa2ub5sULUYaZawjshVWDW3zB/8yie5ZHEHSRIhYsNGDXairSUfcFMXAW9xvKlkZqpcaKqJEuysiDKaeo6OpPzdt+/hS/94H8dqCWnUzmgWpJwRobFul8aWtiqJphhXJzHQXo6Z293JsiULuHD5+Zy3aAGLZrXS2RpTKBSw1uR25eaKjO8tvgINSdxovubFaWOj2htLuRhRthCpx+BQBCdh9ojzHUsPqDqcepxN2HlkhE//tz/hvu391HyRNBXERIjxed2CZDaiIIHMokpMSqsf4l++/zr+1cffR3eryfVIO76VruT7SjDJEvN2wJtO5qnw3jet6j2pwoG+Ub7wte/xD99/iEHaGMyKpKaEN4pIhgWsZkTqsT7DeIeop9VWWDCzjYtXr+LaKy5h7apl9HSWKFkoRGC9D1vG43zNF3l5i5y8YYKi0Lzom/hqwzcjlCfqsfksr5hAZoREPaLgELwqdVXGvOVb9z3J7/zx5+nTLpwUcns4KCnGKEKUS9uGpA8MjcVTdMOsmFng9/7jv+HiJR3ERjHkO49iIXcD8AL2bbZAFA2AXLqcbJPkTGF8k6Che3qPqlJVw+HhGn/1d9/km3c9wrFaQi1qpyYFUiwiDtE61mcUxWHTCgl1WiJYdt5ibr3+Yq69YjUL58+lnFgSFEuWW5k9qhbF5HouiAkadoPdp2qKiZ3D42PcDi0NaSj5UjGXlxq2tJ0GLbbqYeeREX7zf/wVD2/aTd124jXKpapDTIaIxzsQjcLLORRBvNJiM9r9MJ/4sXfzqY/cQEvBkiAEGjdUsTAbnMzG/lbEm2rNCJIqJ3H+msudgRAYqAlf/Mf7+T93P06/a6EWdVAnJnhbpBifEqunZJSiVmkzFdYs6uIXf/J2fv/XP8UnfvQW1iyaRVeUUfQ1YupE+HzZRdC1Mbk9Ocq7PGylhK4OP493KabJC+74V1B+LCoWT5Qv1TxWHVbDIqzRCkqwgT/61HM8vXknadSG8w31INeNfR3NaiRGiUyj9QiDRCxECanGjGSWux9+ir1H+nESkerETIe6cVXs7QYz9YWziaBdBt81j+Ia28Ioo2NjfP/eDfzdd+5nwJUY1TJ1KaI2xholMXVKMZSjiAKO8+Z085MffA//+Vd/gU/82K0sn1Oiw2YUnaeQQcFbIo0xFFBKKGWECCOCDZQep5/RcI1btY4DGafriS8VixeLx+YbNY3mdqDZZKmuypGjfdz5w/uoE1EjRjH5fTRs86jDaIrLqohPm74civIYUrWkxOzaf4S779/AcCUNs0GQGvkAchjcpO+/Hsgp/IvPNiaR+WxXKMgbAQkdperIVBiuGR544iX++AtfpT+1VDRG4hJibC7rBKtQyMZodQO84+Lz+LVP/TN+4afez+olsylbjyULNlUbIybO9UUzPh0EzWrCXDXp0XNNQ8i3nE9wnRyNgid+TKgwgaKBWD48cyb88LHneXLzHqo+wth43NFJ8BS0ytol3Xzygzdz+/VrmNWSEZOCesBivIXMI14hThjM4Pt3PcKuvYdJNUOt5G2Q74hK1iTZXx+aLTvNv79ZMG9mJVQkdyj3GDJEoOoMT287xJ986Q4OjCijHlKEzKVYPNZlJCgxQnec8hO3rec/fuoj3LxuMd2Ro0UyIhHEFNGoiBqDWkHNxEwQhlHD8tCwQk+8f3r+Ee6jisk3ZayCaHBwUomCvVuVqhd2HBrmb797P6OmHbVlXD14AzrvKMbC7DbLv/lnt/Mf/vmP8Juf+jDvu34lLVFKLApOMGqJFaw6UuepxyX2Hqly/yNPMZrWSCUbH8wqBncaJDM5id9MDjXjTVUzco0yRFSoUs8cfSNj/MO37+CpbXtQW8r9f/PNBVcnkZQioyzoMPzMx3+Un/upj7JodgexQGzDRoaY3Iow9YbnGrzivJI6ePixJ9h38GhwglLBRjHOhbYhrbHuwpWcv2ghxnu628rcfssNzO5oIdIU0XRc/w7DSBCxpFGZHzywkV17j+CdBFs25D/DkvDthDeXzEourYKRqerhvsee4vsPbcS1zaTqY8hX86KK1ToFxpjd4vjpD97Ix993HT1loWQgFp9Publ/8ckNDW86VBWPkKlh76Fj3HnfQ9Q0ItOwk+ly99PEQmvkuW79Ou76/vfYsmkT1jlWLprHTVdfQuwqxJIiZIHKkis0CsMU2HloiHsefppKTfPVSZrvdr6pXX9G8KY+kagHn6EINW/Zvr+X//217zLoE0Yo4E0R4y0WSMgomzrdJc+/+OA7+ehtV9MZe4o4itZjdEIHDJrouU1mEcFJRM1ZNjz5PJu272M0M2QSk6YOvMOKw2ajXLJ8IauXLmDHS1t48IGHqVfrlK3wrmsuZWZbREQdNMt3B3OVSYUxYkZ8kYce38L+oyNkABLWJkEyn/Nz12vCm0pmCA1bddBXgzsefoot+3rxSSveFvBYjAgJjtiP0m6rfPx9N/KR99zAjKJSsi6YqNQhprGwYtJS61xC86pfValmwt6jQ3z/vkepUsTHZbxEWAnuqQlV2uM6t123joUzWznvvEU89vSzbN/9MsYYls3v4fKLLiCmjrp6UDNEQA1GDRrF+LiFHfsGePjJzYxmwU8QCREv55Il4nTgTSZz8OqqeNi05zDfuPsR6nEbmcQYhcgajBUkG6OsY7zzyov4yHtvoqclpiC5PpnriGGF3rANn3tEPh5GM+EHD2xk04791EyJTAooBqOOyNeJ3AgrF3dzzbql9LRH3PLOW5BSK/dueJzRWsaMlpjbbryKUqxYG8K/VAlkFYPgcESMpQnfv/dx9veNUMk3xoI76tsLbzqZnTpGUsedD25k99EhXNSCVzvuTpnV6xQjZfni2fzkh97DvK4S1md5mH9+5TFvnsnRzue678Gh3kG+c9e9VH2EMwkZIW2AqA8+JVT5kZuvYl53kYLJWLh4Idffchv3PfYkz23dgauPsnbVMtZetDLsDKprWgAarDiCz3ORl/Yc5v6NT1H1wZaTm2/eVjijZBaa7LIT1IO8HR1CRWHHvsM8sPEFfNwFUkQQ1BhSVyOxddqjOv/8A+9k9eJZJGRYadhMbZM0niyLzx0iN+oVdvDA4RGGq54fbHiaLQcHqURFNLao1oiMIt6R4Fm1cAY3XnUJ5WKCwVOO4Jbrr6DcUuLuRx5j1NeZ0RHzgZuvpNWmqKa4PEdHCJZVxELFZ4x4y3cfeIZ9/Rl1FdSNBauGhtVyc/+ES5vMluEV0anX5P4NvdpYsYSt+pNfpxdnlMyTRv84t8adLMlMxEgqPPrkJvYfGSXTMs6FXa9MQKwjYYyr1y7lhstW0GYzInxostzzbEISNzf9uUHk5o2V4IwfornrHrbtO8o37n6EStJFxZbwokQmQzQjEqW9EPPj77mR2V2tgEFUKGmN+R0x11x5CQ8++RRbDx5GqXL1RQu5+qIlxDLhjy2qoBYvHo2hahM27ennh4+9xEgqYINVI1iAJrbVJ3Wa5HXOPfNeAcm/K2E+yIfRqyPrGeiiM0tmXvlMjcdWVZwXjvaNsOGxp0gdE6H6EEKbSGkvRdz+3luZ0dl5Rkf1mUajo1M1jNTgzvs28PL+g4iY4DetMYktYzJHrClLF83h+muuxpp8a9yHEorFAje+4zraSwXu/+FG6nWho73EB959I21GKajg1ZBaBULZEJLEjFZS7rrnQfqGq6QUXtmer+BzNn6ppHiT4cWPX6k4UuPJxOOFUI6GBaj4U1DrDHThKe54+qE0bMBKLfM88dwWtu4+hJcYG0Vhs0MUqxklybj+8rVcvGoZNs9H0dh3Dl1wBob3aYaMc0OoO6h5w+5D/dy14SmISzivRCYBF0MKRRHarOM9N19FT0crce5jLUZw3mOBuTNncNM1V7Px0RfYufsg1sKa5Qu49IKFFJxDREijcE+RCCSEkHlbYNueg9z3yDMMVsO+62RCT76aaD7xNDKxcxv8Dxu9EKT7K79zYpxu346zSObcmV3zVTcwXMl45OktjGSWjCj3YgNwxJIyoyTcet16OktCnJtFlYYP8blP5ICgUIbokojhmvK9+x9jb3+NqreIifGZYiWGzFPwNVYvmc3NV62laCAxJoS0iBAnMZGFtkLCdZdfRmyLPPDQRurOMauzxPtuuJyuRImMwxsfujePRs+w1LwwXFP+z3fv4dBgPdAvXwt6fWU4r2oEGiH55pV6i/ogfRtpwgxR7k+eYnwFdBQYA1PF+wm1RxsbWk1XYxv8dG2JTyLz6ymweUSd6PuNvSfNP++8J8syDhzp48WdB0lNC94U8N5jBAyeooWl82awZukCylGecCWIKMil8huVzKdbMrwC+W4c+Q5nqoaD/aP8490P0luzONuCYnMbjKMQQ2cJfvTW61gwo0TRgPEeO57MJfh5lK2wbMFcbr7xWjZsfJydew9SiAzXX7aSi86fSUwVfIYQgh00D5FyNqJuYnbsO8oDG5+jWktRr0EKT2qH/PIG9Xk+PR/MecZ7rHdE6ilmjsSlmLQCtUHI+vG1owwOvkxv707GxsZwLmyhT21jbfJbP11tf2Yl85Q6qgZCigmJDLds28nLh/qp+AgvCS7LgzO9IyJj3crzmTujhVjCCh8Nknli0ffWgVeopI7v3PlDjg6nVE0LKQVUgz0YaoiOsmxxDzdcuYbWWIlUG4FOkDenyf2hO8sFrr92LQ7PfRueplbLmDerzI3XrKS96ChKCOQFRSVkUPLGkBrDSKZ85+776RsYJHMe7xXf1LbjV4PXYSgiUkV0BHQY/CDUj8DIPji6neGXX2DXc4/wxIYfsvn5p6lURjCmoRXms5N6VH2YnXMSNwh9OnBmyXwcOO8RMdTTlM0vbWekpjhTyNO/Cs45RKClFHPZxRfSEkvuyD71gaf+fe5CFZxTjhzr546776XiBBeXcZqganLHnxrFgufWm69mVkeJJE8pMO5umvuaGJFgh/YZCxa0c92N1/PghqfY9fJ+RMe45ooVnL+gG+uyMBByi4OK4kTxYqgpbN+zn6efeYbUZbmdfsLKNA6pg1QRUwEZCQTWQagcZPTIFka23s/OR77Jo3d9hSfu+w4Htr/IrI4u1l10KfNmL6FUKmFsQyUMRJ64HFmWUavVxqX3G8UkMr8ecd88qo7//YmGkjDvkXllcCxl6/6juLgQtrV9PagjqhQjYV5XmeVL5iGa5bta+TAfv8UbVTIm1/10SYcGVPN0o85T98pAqnzzhw+xf7BKSoz1gpqMDI/BUlbPigU93Hj1WgqJ4p0Pjv1i8RKhEnKACBYjEVZiWpOEG6+5Aq+O+x5+nFpmmT93JtesW0nRVXNzr8G6iDg1FGpCwRWIpY2RaoHv3rOBo0MV6hqyogZ78wSllSomG4DKPuh9nnTbvfQ+/g223P03PP+Dv+HRh77Hzp0vUGhrYfUV13HVOz/AkguvpNgyB2Pa0NSjzuPIyKhTNzXGGGOwNsi+Y/vZvWc3Q0ODZFmKP45O/Vpx5iVzU7oGg2KN4FQ4Nlxjb98omY0RV8X6Wh4NAZFPWTKznVkdLRhjUZnY3Qvr72DQf4Ue8zpwuhYfzRgvL88SWvWGzfuP8sXv3sOIKeEkxrgMY1MwYLzQaQ0fuPFKZrbHWAvGxBNRWUIe3tUIJgyUK2NZtmAmN167nieeeo69B/uJTcQt11zCkpklkCrOVREJCWuKxiBeSLVA1bby+K7DbNi8k2GviEmxaR+mdggzvJP0yAu4lx6j77Hvc+DOL7Pr23/Nzrv+noOP3U3t5a10+hrnr7iUy2/4AOtu+BCzVl2Pbz+fLO4G2wLE+CSjbquMyQh9rpe9g3t4etuTPPr8IxwcPMiMrk46Ojsw1mAa6/pcLQkmgtcG+1u/9Vu/PfXF04VAtZCVSCRs06oIKYZN23bxzR8+yqhLQjZMiVAs4lKKVLj5ijW8Y/1FFJqcCKYuIs41TK2f+AyMZaCm/PVXv8Oz2w9S0eAN6EXQLCVyjjgb5aLzZ/Gz//z9dLdZChhEbb5BH0KcRFyuP8u4DBJfw0SWtq5u7rvvQayBlSuW0tLWRl//AE9uewm1DicZGRkpdTKpoqaGieqYrB+TDXPVqvkUB3eS7XuCyrYHOfLsDzjw1PepP34P1R3PkR7ZRzpWw0edJDOX0b3iahZfcjMzLriWYvf5SHEm2FaMjTCRwduMVMc4aA5xcGQ/m3Zt4qlNT7F1+0sUkiIXLF3KovkLaY87iKM4+JFIc/rgBnNeW1+fFTKHPlCMBB/eqhOe2bKdOx58htSUgwcXEYrBqqPVVLn9pitYt3whsZlMknOdzI2fqopmNepEPPXSXv7sS9+it2pJpUyWzy1FDImvU2aMD7/3Gq5aez7ticH6EJGCycZ32IJea/Big5kPEDzORNhiG31DFR54eANrL11H94wuysWEhze+SH2sRhEoi6dVq3TpCLPNCHOjMS5K+plfO8SCyh6qz91NtuVB6tufgANbKQ8fIqaG0wzbNoOuC9Yx55IbmbX2RlqXrUe7z0OiLrAlvLHUJaVuawxLP3uH97Dl0CY2bH+Ujc9uZN+hfbS2tnLpmktZvXQ13S0zKEmJxBQBCdn/c4tKEMjh52vt67NC5iBPPCLgRRhJlUefeZH7ntiMj1qDH4FavIadv86C48ffexNL53e9peIhGo0/vlI3Qn8l48vfuofHXtxHlnTlgapgjCeppZS0ysrFnfzcT76PuV0FigKWPPLbkpO4oTuHnbyGfdiZkGfaG0OxtYt773+A2EasXrGMWW0FKr0Vjm3dQkdtkIVmmBVRP1e0jXJDT40bZzreO2uQqzqrdB3bQufwAUrVIaxTjC2TtMxgaOEqute9g9nr30npwusws5ejnfOoxi1UVchsRt3UGTMj9LqDbO3bzMZdj/DA5vt4eOsGBo+O0NM1i0suvJTLV13B/M4FtEkHhaxAoiXCmv/4s+3xXjsVTmsSmFfaDBtEDnZU8KQYjlbgz//uH/mfX7mbNOkJ7ogakTkhpsb8ljp/8dlfZv2yWSSvQ3d6s9BMZlVloJry4svH+Lef/h8cqJYY8iVqGPApkXF01lPKOsS//PgtfPIjt9FZEJLcDwOBzEz1AgwIrp4+nNeiwQ1gpFLh//vLv+a5J57kv/zGv2d+V8yuLXv46pe/SHucMafFM69UZ05So11HidMREhkkSzPSzARbf7kH3zGfwtzz6Vl8Adn5l1Hq6EFtibrGqESIVZAU52sclGMMjPZx4MjL7Ny/jX3H9jPiRqm4Ol2zerhh5rtYtmQZc1vnUqBE7BMSH4eFKSG2tumhjtPTr3zlZDjzZBYAj1EH6kkl4nBF+KMvfJW/+NaDpHF3yLnmLZkXIq1yXqfn87/3y1yypJvoNC/OzgYaZD5UsfzhX36Fv79zA32+lSxpD7YLn2I1pSsb48JFbfznX/8kqxbNoIwhIkLFoybFkUAj3YBvRNNkIGlIVeDqUB2FsUEYG+SFTZv5+t99jZsvW82sYoWoPkxl+BglU6PAGAlVEhyaZRiFY1FCKkWi1rnE3Utpmb+KlkWrKM5ZBOV2KtKBYkFC4sq6jpD6QXqH9nP46D5eGN3Nkb5DDA0O4FEKtkR7uYulC1ewdPFylsWraInCU5nUEEkUuCu5JnFK4fva+v6skDlk9slAHXWJOVQRPvO5L/OlOx+nFs8g8kCeXSimxvldyl985t9z8cIu4rcYmRuWDOccD205yi//zh9xsALHsoQsasGIIfYZNqvSwyj/9uc+xI//yJV0JY7ERRgi1KR4qYTTqQCTOSRLwdegNogb6aM6Nkh18CDSfwR/ZDfVvn0MDg5BzVKqD9LmjlCwGUYyTKTYJKEeFRkxbVSiGdiWHtK5y2mbuZAZc5cRz1iMxh1oqYyzEmzSeFIyxrIRjo4eZe/AHrYe2cKuY9sZSofw6hEjFG2R7lI3qxes5eLZF7O4ZSkl1wIGIpPHcJKnBTMeh8PjKfrC5MZ7BblfW9+fVjJPRaNuHsnzYmRkEnFoTPkv/+uL/MM9z5JGM0JAq1jURMRUOa+jzud/999x8cLuc5vM4nPbr8ndPX3IFGoj+oZH+U9//k2+89CLHKvFuHIL9axG0UKc1WiJlNULSvz+p/8tCzpj2qiT+BATia/gGcVUqzA2QnWwj3Swl0rfIdLBY1T7jlEdGaKUHiVOBylkgyR+BJzHugLGKUWTUrcJNRVqpkjW0k3aNpdo9jLaF11E+4IL8N1zkaQFsa1gijhryaROXUeouhH2jR3g0MAhdh7byZZDWzlUPUrNZIgN6vzsejfzeuaxdO4yVi+8iNmleXRoZyCyB289Rky+TxAksZdAZI+n4Ccrka/Uk19b359ZMuc2OU+eg9hnqDEcHPX87ue+zNfueo7UzkCB1FgyY4gZY3Frhb/4z7/E+gvmn9NkVgmBoaIhzxvqQAzDGTz87CZ+9b9/kQNDCd60gVSw6THKfozEVenpKPFrn/oAN125hkJWxYz0Yip9ZKN9jA4eZXRkAHfsMH5sGFcZRGqDmOowxSyj4D1kjpIOY6IMooxwAopFaaXiS9SlyEC5m6i9h6hrPq3zV9Cx+EJs11xo6QSJqRUjXM60jJShdJje6hH2Dezl5SN72Hx0K/1jfYyZCvWCIxWl4BM6XQtLOuZxac96LliwnDmt82gzndgsOIt5KyCK1bO7fD/zZEbG3QSNz1AjHB5TPvO5v+Urdz1HzXaiQGaCO2EiNRaWKvzBr/w071y/4pzWmZsXZ4awJqg74fCo53f+6M+546lt1LKENoHZyRDz4l5m+CHaIuX8hfN53/WriNIh0uFjpAOH8CNHsVkFcVXEZRSy4J9hjcNIitEMK4pR8gz7EZm11KwlMyUy04ov9CDtc2mZOR+7cCVts+ZR6J4F5U7SKCGzMRkRCoxSp+bH6B87wt6+XWw7tI29A/s4XOllJK1AUgEPiU2wUqBgWlnUvpBLF65h1bxldMezKdNCRIHYJViNERGcDX53VkP20tOFqZJ76mbXmSVzfqCky72+jE/BGI6MKZ/9//6WL9/1LGO2E1HFScjNmUidufEo//FnPsRHb7tq0qbJuYbJloYMj2eoCj98Yiuf/oPP83LNUDCwyIzwvhVFLiocYHHUT1IbpRTFqKtiSTF+lJKpkmiVyGd59iOlWK8FXS2yOBEyG5HZBCeWusJw2kJWaIO2HkzbXDrmr6A8+wKKcxZjumZBsQMXWTKr1FBqpFSpMlwdYXRsiB1De9l7ZAcH+nfRnx5i1IwySoazMZkYCmmduBYxszCb+a2LWL14HStmL2decSadUiYjwhIRkWB8TlwhRLfgMadZMr+pZMaHbWcvYS/HaIqKcHTM89//6h/4wg+eYkQ6MSgOS4Yh8jV6ZJif/9BN/NJP3k5rcuaq90ahmnsyCIhkZKocHHT8x//219z75E56ozItNmPuyC7ev7DG+xdXWVjbQUc6QOyVKiXECupHiW0NS8jMbyUBSYjTITxK3RSpx62M2lbSpANXaEMKZeKWxbTPWUz7gqUwcyEUu6DcjiuUqFqLUKfmqoz6MY5Vj3F4+BCHBvaz7/DL9PYfpb88QpURMjNKXcbAWlQLRNKBdzHzfCdLOhZx0fw1rJi9kjbTRdmWKWuEyRQXhcyphjyHX26lOBtknkpkTkTmE42AV1orTgFVVE0eUgORpihKbxX+7O++zZ/+nwcZMV1IeHQyibAupcMP8r6rL+S//LtP0NOSn3Otmu8UHf9BXg2m1v31ltOA5rmVvYZdutHUceeGF/j0n/49B6tlRpIysRtlTnU/a/xOfvrihPXl/fSM7aNYq5KZGMQTSYqYOt5YMlumbltITQtV8dSI8EkHvmU20rmA4szzaJ+9mLaZcyGZCS0dUIjROKKqnszCiNQZTisMpfs5cGwfLx99mV3HdnN49DA1qZJJhhfFFWqoBRtZrCniqxFl7cRWylyy6nKunXUxC9rn0mk7SFyBiASVkM8OdWAKky0QZ4jMr7bfzjCZ8w7Pn9P4GkZgMIv48nfv43f+8tsMSydGPU4smcSIZrS4IdYuaOdPfvMXWDG/c/y+5xqZA5HDBocHDvaN8e/+0x+yYUc//babzAgmG6MjG2JBbT+3zh7kI8szFlW20p2OYrSKSBqy9wM1EzFa7GEo6ca1zqbWNo9S11y6551P6+wlmM6wePOFFlIssSmSGmWYCqOMMJIOcmTgALsO72J/70EO1HcynA5T9TWq1EgjJfUep2BtTCGLEFNEtB1NWxk96hjaM0wyFvGvPvEpfmTFGjqTMpGPxjc1vAmrIKMeJA5WirwZxTRxBX3NvhUnwqvttzNOZo/gJM8r52sIyoiPufPxTfzyf/sSvfVS8DEQQyoJ4CllQ8wvZ/y3X/5pblm/Cmst0rTteaKHORWm1v31ltOAw4ezuj1UavC9ex/hN//o8/Qms+iXDiJfJTIZ1OrMlipL05f4zR9ZwLxjj7AwG8KbKgaHdeGMv5GojXrPBbSuvo7yktXYtqVQ6oJiK9gYnxSoiOJEqOOopzUG0iH2juxl66FN7Dm8laHaMYazEeomo5IMI4lBRalnHiHG+ALiI8gshdoMxsYSjhwVjhx0DB3OkCFHSwq3Xf8Ofvtnb2d+9wyicM7A+OFHJk/upRpiNpshDdZr7l12GvBq++24LqDNH27+fWqhp0b+4HkRmtuSjcDczhLdJSHSNDffmXynMDiLD9bhua17qOapHcSHE0nRRjxdaNjXghM9VzO06aCdUyHygnVQyWBn3xBfuuMehmyRqg8yKcZgcweqVAwLVq9n2XXvp9a+kDEboSa4PmIiUlum6iNq3tO2YAl26eXozFXQshAfd1EpFjhkhtkt+3lm6Bke2PlD/uHpL/O3j/wV33z873hk971sr25hr9lHb2GA/niUSrFKJik+tRRpI6kX6HJddFbm4w/NYttGz9P3j7DpsZRD28vUBmaCn0Ndu3jkud1s3X+YMQ1RKqIuP1cgT6be2L5raqbJvTFx2uwbxast57hkpqlT3wgk91ENsaiKx+IkwhphdluRRT0tJCYLwZRiwkE2miEiVFzEE5t30Dday/OnNRGxcb02LsOreK7GDPCqBm4tQzxUHDz4/BaeO9jLsC1BVKCoSsjJH1GMhBmtER/5+EeZecE6WpesZTgugzqSbIzYV4k0o2wyGNjHsV2bqWWeuk1wUUzdeHb37uLeLXfz5Ye+wJce+mv+8Zmv8dCRe9hcfYajZh9jpSFqrVWqxZSadahEaM1QrLXSVp1Je3UOiwrLuWLBtVzUfRW7N45yZGfM6LFOqM1GXA9W21BfIDMljo457rjvcfpGHJkTIrVYZ4m8xfrQH8FzJOToCHk6mhwsmprvVbfnSfBqhMwJyXwiNHf21OtkMAjGBNc+awzt7e0sXjgfl1ZDbiMRvAoqEV4iMixbd+9j8649pCJgwwGSkxqpWSycBTQ/p6pCLNRRjg6M8IO7H2BszCNSCNu3oqhRjHjKkeeSi5azetUyolKZJZdeg8xZwZgpk2LBhzCoAp6iq3P4pefRIy8TUcVLHS8pvQNHefq5x9l7aBtHay/THx9kNB6iEo9SjSqkto4nIzERZS3Q6gvMHZvHrJEFzKufR7rNcvmsG3j3RR/kXWtuY3n7EkyaEFHKt81zbzxjkaiISoGHNz7Ptl37yTDhrG8JzmKBNqde3L0aXpxOvGYyvyY0jdTGMzVCzpMkZtWKC7Bax2iGdy4cTEmEI8KZmN7ROvc88gTDdaWuTATDjS8rTz+ZX+3gBHCRMOIdDz3+NM9v2Y2XFryP8c6DdxgLmo3R02L40HtuoqUYo0kR5q+gvPJaRkszqZoCHg2RJ2mNsqYUho8wsOkRTG0AQ4pYYebMObSUWsh8jWo0ymDSRy2qkNoUJyE7kfWWclpkRtrB+cli3jHnRj5w8Ye5/eIPER1s5eATQ7SMzWJheQG3rL2aImUks4jPDwU1+TksGuM04dgw3P3QUwxWUqre402IJYRXNy2+mjY8nTizZIZmpQDUIzkho8hy4YrzmdvTinG1cFY1wQFdsahEVCXhsU072HWoj0oGqQ/OL0GGNGLGTh+mNv5UYk+d4ioKh4bG+OYPfkjVJ2QUUA0ujiH3dIrJhrl0+UIuXXkebcUIbALFGbStvJasZxlDto2aRhgjWDxFTWnPhhndupHa4ZexWUpERHf7fK5cez0l044xMVKKQyygWozGRFlMS9bK8s4V3LLsFj687sO8//IPcs3y61iz+GKuWn0tzzy0md1bDxILXHfVZczt6CJ2YJzmbqfhFHCHwWnEmC9z/8YXeGHHPqoOMm2sVXKc3uZ/wzgLZM6RJ9czucEmiWMWzu3mynUriP0YieTRyLncVQyZLbP7yAh3P/wEVWdxfuJg91Dm6WvNqUSeimZCex8cigZryt0bnmT7vmPUNSacxm0xErwkIl9jQVeJ9910JTNKFuM1uFTaVuhaROfqdzBSmkctbqOmFowlUkfZD5MM7qb3xY0w1keceWJKLJ1zEWsWrqcl66Lg20h8gcjH2CzCpDGt0snlF1zFtctvZF3PpXRHMylSolhIeMd114AxPLjxMUbSjJkLurj1HVfQFkFBwHjys8LzqA+UKgkH+yp8/95HGBjNSH04NSvE500Ik1c7k51pvGYyNyviU6/jo0kyT7naSxHXX3ERbQWgPkZESGPbqFTFGca0xD0PPM7Olw+GA9DHG7uJ1G8QJ+qI4z1f46eI0Dec8fXv3sdAxZNJFBJ5G8WYkCEzyipcsnwx16xZSezq2DA54SRCix10rrwGO/dCRqQFl5TJTBQSKPoxCvWj9L74ABx+CdwIiRe6kx6uvOAq5kSzKY0WERfyTjj1OFVGxsYYHhyjKGUiVySqF8CB1zpz5/dw2eWXcO/DD7H32CGScsw7r1/HvBkFElKsKsaHJOVCOPk2iwvUSHho47O8tOMgtcwGv3rxYIIVqrntmmeyE7XpmcRrJvNrwysJ3HzFxrN6+WJWLz8P40P2y0ZshQAqCd6W2bn3MD+46z6GR+oNWXDGiXwyiAiVSoX7H3qS3fv6yIhRa0Pkh9GQ/AShp7XEj9x0LTPKMQVjgllLTXDslRg6FjJ/zdVI+yx8oUwqBiceoUbsR5DBHRzc/ABUjhCTUiZiSdd8Ll2yhs6sBa8ZqdSpS42qqVOlxuadW+gd7scbiDQiIaEglkJkuO7aqzFRzF0/vI+xSpUFs1u47so1JOKwecraUPPgf54ZQ2YsfQMV7n3gMYZHUxQQ8SDp6TIjnzacWTJLg3STr0Z+34II8zvbueXK9bSYcO415FmPbKhcmkLdlLl74ws8+MwWxnzYeQsHT+bulzohqYOKQr5QCdQ/EU5N5JBwRUiDH27+8Vrq2HdsmG/fvYExyri4jcxFiBciUayv0mJqXLVsNtevW0FkBayFPAGiYLFYXNxGadmVFC64ikEtgXoilxFlkKTQJnBo51ZGj+0HXydSS7vpYv15V3BB+zJsFqMOrAQCZnGN/bW9PP/yU9SzEfKxhXHBXrFk8SyuuW4dGzY8xuF9o3Qlhve8Yz2zOmIKiWKsC45PqjgSnEupO8OYa+HejZvYevAgVfUhcU1Wfk0C5cQz94lx8hn/lTijZA6kChkjVUKeuBBSbjBiiBA6CwWuuWQNl6w6H80qIQOONTivWAlyIjVl9g45/vZ797Nlbz9VB07DBso4X5ufWcILr74ZTgLRcZNU5h3OKzUn3LPxObbt76WqCXVTxBOHA7CzOlardBUcH3/P9XQVBRPZPJuQD4SWkG5QTQHaFtK64jqyjoXUSUi1QF060HgWng4yLTE4NAYqGB+R+DKzy4u45LyraNduiq6IZJBYgyaekWiQZ/c+zZ7eHVTNMCl1rEREonS0Wa6+Zh2oZ8NDz+LqGSsXz+X6y1YSMYaQhoQ8CJnGYRCrpaYtHBxM+e7999M7NoxzQJY7F70KvBZCvhGc0ejsU0I9XoWo1EpVLU88+wIpeUZQUyTLU9+ioM5z9NABqiODXLRyGS3lJGQdbtbZGv81/XIy2XEyyaz50WaCIHkSb+c8SszuI4P84ee/zL6BlDQqkknQ4406IqlT0AqXr1nBT/3oO2kvJyfUIzMRxHuSoqXWe4jR0VFGSRiKZ1BpW0Db8qtYsP4GZiy9GApdGCmAc2CFYmsLR4YO0zt4BJdkuMRjogjvBFcNg2bxrPOJkpCXIgIy52nt6uLgoV6ee2YTV111CW1trbSUWnnk8WcZqkEmcfA/FwXqWB9hsYhP6T+2n/VrVzG7q5OCWDTf2p36XM1oXmuc7HPHQ3ObTdXHj1fWWSfzpMrkoTQmjmjt7OTwsWO8vP8QTmMyn6BG8OrwefrU2Ebs2L4VyFi2fCnlgiUSHyRnnpRNoEnrfn1kbnSAD2I01yE93sNYavj6XRv43sPPUo3ayExERnieSDIiN8rMsuFTP/URVi+eSZLPfQ0nqWakCGCIorDFv+vQMbRjHjNWX8uCq95Dy+rriOevQONOMC0YDZYSFYO1RUrFAgcO72XEDFK1tWA28waxhiNjh5nfvpjuthlECLFajLFEUYHW9hk88shGKFhWXnAeszva2LNnPzsPDjCmCZkEd93gUBRhCDmia9UREhM2gFqSyaQ6Xlseb9H8WnEi4h4PZ53MzdBxA49SKhfp6Oxg4+NPUa2B9xZPTlIsiCVzHmOELS9tpthSZOWy87FBFwkJBSHX0yeIM7UZTjaym6dD1eD3pRLqJyiZt+w6PMIffP7vOZomVCUh5BkKhLe+hlT7uOHSFfzkB2+ju2yxBNfV40kmlXCirBVL1NJGqWcuc1etp+PCK2DWBWhpNhKH44dDUGjIt2fEYqVA2RYYq4/w8sBu6kmduveIszh1DLkBSqNtLJm7iDZbDmQOx8lTKrfT29fPI089w5WXraWnpUCpVObhp16kvw6pQiQpKIHIBBXRq3L08H6uuXwt3V1lEhMcwMjb9UTqxIna+9XgRN9rHiCNz7zJZDaoCEY8sVE6WlsxJuKZZ5/H2ChYBwAw+Fyby3xGPa2zfccuioWEBfPnkxRLOOeJbGh4adrobm6KEzXM8SASHGq8BzVKpjBah2/c9Sh3P7GVAV/ASfA6sSIhqQt1FrRF/PxHb+eS5fNJxGNy19Xj3bvxmsdCXKQ8YxZR+0xcoYt61E5qS+FcwNx23TThYBUSiSmWCxzo3c/RyjHqkoEP+eSMKOZYwvz2OSzsmk9MASMR3kMcxxRLJe5+YAMzOju4YMlC2tva2bxjNzsPHiV1hDO5tUFkH8yiYsnqNVoLhovXrKAtniDzmcTUexxP0of+ehOhEqSTVSh4x4zE8P6bruK269YS1Q5T9FUi5zCaoWRoJNRtTBq10VtJ+JO//j984Wt3sO9YhZQYpzYvdELReCMQdVjxeCwpMQf7Rvn2PQ/TV1VqPhwLbMUQiSGS4K99/fp1XLduNQVXCSd+N1J1HUdqWc1CjKMRnCniozZ81IonwWs4L1zIz+wTRU1wvtfcpbZgEha3LWH9vCtor3dg6kKEpeSLtGftFIgY7R8mq3m8ExRLpFASWLFkAesvXsudd9/PkZEa5fYi733XlcwopLRYH9a8GuX3TXHWkZqImpa48/4n2Lmvn+N4D7+peFMls89HVoRivCdCKRSLzJk3l10v7+Lg4X68JnhxOOPJcIgxqFokP2Jty+bNHDl8hPlz5tDd0YY1+baKSK7ITGDqCD8VxKcIwohTRuqOb91xHz/Y8DzDlJBCCyJCRCMyu87crhZ+7sffx9rFMymYGmLC0W4ngmg9bO9LMNuRu8ya3NUylN+IclecUTKCJmVUUOOwzlIqljkwsp+j6RG897RmLSztPI9rL7yOixZeSHepBytFMCa442aOKI4ot/Vw94MbSFpbOe+8eczs7mDr9t3sPThAlkWoJGBSvE3xRkBDkktfHaW7o8xlKxZQSEJujzOJV9tvpyRzs05y2pFPDSZfaKFh96ytpcjiuT1s276DvqFhnGbBRdTEqLdYInBCpg6NYnbtO8SWnXuwhRKdM7ooFmNw+QaLseMuSUrQrxskH7dJj7/UsFOHJZ/RKqlm1Cjw7LYD/NkXv0FvLSKzpRD3l4KYiMxXaJVR3rt+FR+/7UZaY4+NPUh0UutnaNbcXNk0VTZMlyL5bmh4k7AYbXwGxElY1CUWRTmy5wg90sPlC6/gxjU3c/HsdXQXZpJQRMSOK2BePcYYWooldu09yJPPvsCll6ylp60F45WNT29mNI1wxuJNyGkCEOGJJQQp9w5XueKSC+joaENcStSw/TT8zBtrmNeI18q35s++KjI3/zydEMLCLfSMgfxkJauO2Z1tzJ4/j+df2sLgwCBZBtYWMcRYiRBCYsK6saSmwMH+YZ7etIV9Bw/Q1dlBV2c7xlq8an4nDc7/DUcldeORE+PZ6XNofkBN5mqkYjg8mPKFr93JIy/sYcwXQs41I0Qah522uM6Ccsp/+IkfZdX8HmxscJZgVz9Jl4oEyS0NvoYXJ658gEmeaD0QOfxEBLygOFJS2oqtdEkX6xZdyvqllzO3PJ8OnUGshUDkpgVy4/dSJESFEt+/535mdPew8rzFzO7qYtPWXbx8dIhUQtZRL3GYLTTFSIaXiMGa0NMBK5YtpTUWrE/Hj3x2uTPSiYfx8dHMsVfDt6mfedVkPpNovof3nigKYevdM2cxb8F8du3cwfDwaB5vZzAmCqtrG05RUhPhvFBPPbt2vczzL7zISCWjraWV1nILURTswKIuxNv5DMGNezE2TG/BtjJx3pIzBYbSiLseepovfv0ORrKYzBRwJsojzg1CRkFHeedlK/nobdfTmkSoQArY8dOzjo9X27Yn/JwCElwzC0mBObPnMLNrNi1RKwkFIo0n5T1ulnoiglFPqb2LF7fv5oVNL3DJuovo7umm5uGJZ56m4mw4ONSE71gJs2ijvQcPbeOKSy5mZkdLUIdys6Hm93itZH6tmNou5wSZye/TMF+pKtZaokhYMLuHZeefx4H9++nt7Q2S1AQPM29iUm/AxGTEpE4wcYn+4SpPPb+Np596lqO9A6QaQ1TAFgrhexKOOvZ5409WL4J92QPHKpYfPvYif/z5rzBYj6hRxJkkPxk2nEWSUGVOC/zCx2/nwgU9RFYQK3g7btQ6Iaa27fEWiRznc83Iqx8WosQUKBKTEPskV1UmyDv+nUZbZzUkKlBs7+KOu++ma0YnFyxbSndPF9teeoH9xyo4laBmNFQfgvRVsaSjvcya0cmFy86jXAjSu7HbK6FaZxWnJPPZRKORaUhoccTiQoOtWklldJRDBw+SZWn4bE4q5wWHwcRFqil4k0BU4tjACM9t2cmDTz7PEy9s5WDfMP2VlCoxdVskJT8vxIT89JkYUgzDNc/Lh4/yj/c9y5996VscHKgy6mK8LeJNSPYNSmIzSn6Ed61fycfefT0dRROGgVgyDZLsTHboOD8VjASPt4gY4wxGo1OKRslqiI0pt3eyedt2nnrmGS677BJmzmhD3ChPbtpDPfM4tYiNcx+YMILCSSxKf+9RLluzihntZawNZA4L2WBROps4bnT2mwlpOk7LBPlJqkLVWw4P1vjufRv56vd+yI59R9FiF1UKpMTUNQrBskYwmiHqiDULAbI+xWgdS0pbOaa7q5U5s3s4b24PPR1tzOjooFwsYcQwODTE3oP72fLSS7ywb4zBmgVJ8CYm06BxKw7E0xpXWVj2/Kd//QneedlKijZFjAIxTvOTVadYVE4ngp6fO4oHnaNh7wSCffxkEF/DqWVMY+555Cn+6H99jo997MO8+13vYLj/ML/xh1/nic17GZFWUinmkj6cBuZFKImnnPbzrz/2Ln7qAzcxozXJz3HMF6knv/1pxzlJ5onpVoPpSsMKuu5gsA4vbN/HP3zrezz87HYG6paKj6mbYrA1ix0/GCdIrhBZLA1S4xCfYQyUIkjys6nFe8h3/BAh9Y5RLSFxG5VKDWsteZh4sHmTUciO8hM3X8Fv/dwn6C5H2FhBspD8xAXJOB5mdAZwqqJPFdmkmmEwpF44NpLyX//ocxzuPcr/82v/hgUzW/ny957kj7/wVfqzFkZ9EbFRiNc0wYkrc5Y2P8jaeRG/8x9+ltVL55NYQyQSIgRPVYHTjHNKzSAnc+PSPAWBEUVCmkASq/R0tbN2zSo6Ojo4duwYgwP9IEKWxxdqbq1oSK0GQYOuHeEJK/QaBSo+puJiqlqgqgk1KVGVIjUpktkSqRds1LClOiALBzySMadD+Nc/8UHWLJqLBXwkeboEwOc+rGewPyeKbrqJKN4oKi7X2E9cgSzYhLCqxFFCVGzn3vsfYs7Mbi5YtIDOnlls2rydw30jqC3lsj/EmiBKnRIJGdWBAyyY2caKCxZTiG3YET3Fvc8ETknmBrHOBho7ZeMXQemUxkyaewpEVuhoKbHsvCWsvXA53a1FBo4eZHSgj0jId+NCx4rkYfD5BBS2hS1CWESqsSARaoOa4sTgsHlaBCXF5ws+S2RjtF6jNYISGR+76RI+fMu1tBeThuI6bj6DV0aTn268gszj1rxw41Nt8IqEvNIiAsbQ2t7B9h072Ll7N2vWrWduZ4HK6DDPPvciPipSdUEQGFVi7/A2wmgd8Rkjg31cdvFFzOxoD6dk5XU4m3hVZG7+eSYx9R5mfAEVyKH5StqIwQDFCGZ2llizahlrVl5AWzmhOjLI2NAA4upk6kAmFmKq5EsTg3qCKU4a0lzzk0PD9CiAI8sd8oNdQus1OgsWP3SUKy48n1/66HtZMqsTUKwNdRqXhmejLxv3mHSvMKBObkcJCEfWNcxpECcWE8fc99DDdMycy8XnzaSjvZXnN7/EvqODVKVIJjHGC5G6PO9pWIhXRsZYOLubCy84j2JscVmGsWd4apqCV03ms4WGU87x7tusgoQrwxpPFAk9PV2svfhCLlm7kgVzZ6DpIIND/dRroxifhjOnrc2XY0E6w8RxvuHKN1AI0SvGhACBWJUiGa0mRcaOsm7ZHD71Ux/mkhWLKETBkeh4zi/nOibVVUKzdHT1sGXrdrZt38alay+iZ9ZchiopT7+wlaozIX5RJGRpIjfbYVDvyMaGuPqytXS1lMKccIJ+PFM458h8KkwiMy4/+NETWaEYG2Z2lrlo2SKuufRC1lx4AXN62ol9FcnGIKvhalWMD4pESDnlMRouUQ0umxr0yEhTIl8n8XVKvkJPyXPz5Sv5+X/2fq66eCmtcRD3zXV6K0HyGUQkaEmZgk0s5dZ2HnroITpmdLP4vMWUS6088eTTDAyP4bAht0ZjxjYRmJhIYHTgKPO621i5ZCGlxIap9SzilGQ+1zCJMLlKYLAYFSxKIlA00FkusGzRLK64eDk3XHEx61cv47y5PczpbA1psGqDaFpFfB3jakQ+JfIpJqtiXI2EjMRXSbIx5nQUuHbdcj72/pv5+Ptv4cIlM2m1GVYMxoTr1WDqpsgrZ5qTD4rjff+NoHFEG4RoHucdxhja2jvYs3sPz7+0kzWr19DT1Ul1bJgtW7ZQS+u5W6sSa0ZkDVaUSOtE6TC2NsRVl15Ee6mIhMjeM4pJ7XaumeZOhUkd2JzUaNxOleu/KEINxeXpviLqPmK4knGsf4T9Bw6zZe9hDvUOcvToMfr7+qlW66RphoihUCjQ09HO+YsXsGb1clYtW0RPR4GWSClIOI5hqiPRVLKdCqci42st77UiRGPr+JUpZGJxAg8/+hS/97kv8i8+/uPcdM16KmNVvvyN7/HQ05vZtvcotcwTRzGpGuKkyMzOMhfOa+ed61fxIzdfzYy2Fkx06hRebwRT2+8tTWb1TYn6YFwKBA4oRuthgZc7wASjUn7KqcKog1oG9XqdWq1OpVIjyxzGWKyNaC+VaG9NSOIwY1pxWDSPhm7Mz031eY3km9oZU/Fay3utmCBzI6GLUNdw8mv/4Aif/YuvcnjvDv7Dv/qXnL9oPjUv7Nh7kF17D9Lb28dYtY5EBTq7ZrBw7kzOn93Ogp42ipEgYrBmmswnRfMDeNIQWpUv5yXsUgSTnoLku3AN1a1hsUCCLdr5cI6d5Md7qea2LQnlxLlNwGsdrxk2suMH1oeunzyLnop8Uxv/VJha3tTvT33/tWJi0yUns4DDkKrBKTy45TB/8ge/y42Xr+anP/5hWltbg+1fFZ/WySQGEw7liSSjbMKB9UhE6i3RSXy5Twemtsc5ReapFgGnHmNsEK6NjRCxODVgFK9pTtTGQ002BXk1mPBR1GcYCTuDIe1B6BTTaHCVPBceqGaBz96G0w5MsCGrCbnYGnf0EFxKNXBBxeElDdZwXwhljptK8klETSgT0EjD1jiaD8QJSaYSNs4VO56FzEqWB48ZnNqQE0MUvAMJSQ81+LUhIR3jeHnHhffhMNF8VKpUMeIQH5HVhAESHn3oQWojx7jpxutpa+9AjMWKIvlpV5KvF8Y9EiV4NnrsKXcoTzfOWTKLCA6HaiCUep+TLMZ7MJEPcW5NHTZ1pDaS/Il6vMuwRkIHStg8UYlyEofPq9fg8SYZma+H0H6vIR5OBG+inMDB6p3l6QWMKqglNY661IiISdIEUVCT4U1w08y8I5IoRFl7wUcatofRkMvZh0PiNT/8MURBxo39HgxVVOs4YpyUwEHBgvH18LwmDjGVCqLZuEfgiSCkOBeTqaAGxNZQVyHWCOsL1IkxmoLW8SgkpUBmCMdH5077DUwVRm905ni1GL/vuUTmZogIqhn1DEZqwssHD+MUYmOY29NFWwmSyAQH96bvTIJA3Sm9gyNhW9rGtJYSCiajFOWsyVUKxZAq9I9W6R8dxYnQWYzpKiUUIoMRQe1kMjsYN+mlmeVotU5/rQI+JnFljNTBZKhxYBxxDC2liGIsWByWYI81+JC2S+PgitpEZjTGkUt+reBRhmuw7+gIzhuKxrFgZgeJFeIkHJhjNPijnJLMWgERqmoY89A3MIzLFKvQ0dZKOSmQGEckWaiTiYEo1Nk7mKITn20yB45M3OOcJTOAkFFN4dEXdvOZP/48g6NVutvL/OJPf4wbL19JZCTYORufn6pDiWdwrM6f/83XeOy5bZTbO3n3zdfz7usupSPOCD77FhQ8EWMOvnnnA/zDd++kSsxNa5fyr37qx2krRBhRvAmHQUpOZq9BFRAMvSMZn/3cl3hmxz6cj0k05F3WRv4842kpRSxeOJN1Fy/n4otWsnBGO+UYYkmD8uJDFlGfn9gU4cAHvxAFlDp1hSc3v8wf/K//zZGBUbpbE37tF3+GNcsWUyrEuR7/KsnsqjjJGBXhwSe38Fdf/A4jo0ocK9deewn//P230lWOSEyGtYKSoITD3I13wdelCW8GmWm6zymUqleioQJMJc7rwfHKmPSaghhhNPXsOjLC9sNjbD/YT8Xlaa5y/aC5PpPrpzjn2HOoj2e2H+TBZ3byx1/4Ohtf3EmNOGy5eI/zIT9H6qFvtMam3Ud4dlcfuw72U3fkvhmSnzjbVLecKJl6agj7+8d4fkcvL+4Z5IXdB3ly+8s8uW0fT2w9wBObD/PQ0wf4+g9e4LN/+l1+/Xf/nh888ByDY55KFmJdJqwK+eWb70XQq01MxRm27TvG1gMDbN3fS8UZxE4JLJXwjamY1HeaUEuFoTHlH+98lOd3DrFlb40nt/bxtTs38tzWndQxYKNcb8/rp7mOfxzoKbPCvn40920zTxp/T6rRmahAMyZNCU3kOxkUgSjGx2VS24KzpeAUpJwwJGgSxOBNgbppZSArsOPIKH/+pW/w0oE+6hKjJgZj8LkfBzYmkxI1acWZIo5G/F1D4tF0IECuJKjHW8HZCG9bICpBbOjoUjo667R3prR1OOJSRqoZgzXH89v38ft/8r/522/ezVBVqGY59/KFn8B4+FHgpA+nBYigUYyLiqS2jI/KIRghH9wT/tOvbIupBPBqwLayY88Az7x4gOF6woiLqdsW9h4Z5Z4HHme4qiGPnti8xNzp/gSru+P2wVnC8YfXOYN8XS6Cx6ISB4uC5LrucTpsKhTBqZCqJZUiLulkw3M7+LMvf5O9vWNUXMjIr4TzR4IFwaCEs1XCKVihpAaF8+GTv944PsGNm/lcWuOyS5fzmd/4ef7nb/9f/I9P/zx/+Omf5b/+xie4/dZ1tJVqWEY5Nub5/Fe+ww8feZq6hkTezffyEqKjA8kdiEPxeBGcCE7seOS0aejveR0nyjoxfOQZy+CHDz/NvsOD1I1n3vmzsQXFqWfDE5vYs7+P1BlUg4NWY6A12qIZJ5KcZwunfuI3EWExJI3fcuk48V6YSk+GQFKfe4BKVGSwkuGSNu548Am+8s3vMjRWx9iQ7ETE5ylsG99uhGbRROFXdmIwbQVri7oUdRV6uhJuunA1775oDbetuZBb167g3VdcyC//7Mf5jV/8GRbPbKeuMf0V+Mo3vsvh3gFc0+CUXBb7xh/43PIRolxUJs7lE0K9wYfAhEadTgE1dV4+uJf7Ht5IihAVPe//4A0sWzEba+oc6x1hwyNPUakqPh9VJyIyTFYxzvQsfzxMIvOrGU1vpLLN5Z+onEmvj0eMhE0Km3uoNVw0YYr/c1NZ4W8TXPrV412NmDF62iOsgZom/MP3H+Kb9z5Gfy1svahPicVhNQvJUnwgybi+qEFijt87H08xIC5IrpQ6UewpWSHKy7HeEvuIdhszpxzzritW8ZO3v4Mkyqi5mC27+3h26y5SDfndRIOtoxFHF24bUhkJhB3KqIAxBQwGzTJU882jfMYKxzoEG7jm8eeqhFGtwUI5Vq9z/xPPseVALxobLlzYwa3rFnDD2gsoRhEjGvODDU+z4/AQdW+xXjE+Q5QQFX+c/jseXu3nToWpfT31Ouckc+OhVce7IOzQERaD5Lt1k/XD4+v74aD2sJulWkfrA1xzyQpWLV0A3tE3pvzNN+7kyS17qLhwMI0YiyE/uzA3u+Xbg80l5+oIgAt2XW9wavBGEatEYlHjcNbjLKgRYjEUyegseN5xxUoWze/EK4zVY7a/fIiazxXn/FaNOSEsuxqDWEIsnokRE4WcGurzU7xCHEgYEI1REFqp8af3Dq9QTT0Hj9b44YYXqEuJxEa8a/3FXNCWcOv6dSzo6Sa1CTsO9bLxuS1U6o12CJs8vlH8aSTrG8U5R+YzBQFaigXmdnfwiY99kBULukHhSF+VP//CV3lh52HGNJzh4QjZhE49T50cE8pRuL8RTyQei2NGZzvLly6mEBnEGPYePETdMa46GfJTBE6GxpniJ8zPMfGqAEoGRkk1IzPKxk0HeGnnUWJTYG5HJzdcfiltkbB8wVyuXLMCayDzngceeZS+kTGy8Q2mhip28vqdcnF+mvFPhswI4DOsr3L1xYv5mY++j7k9M6hlhue37uMLX7uTXUczRlyRuhO8C1nk3xjyANmGlPVZ0Hd9SIQ7o7Mt2LpVGB6pNp2mBZbsuPp5M5Q8le8J/YYbwQhBPhs8KsGj5djwMN954CmqvoBVz5VrV3HevG7KkaetCO+4Yg0dne04YPP2nTyzZTujLpykq/jgGvAqcDZI3MApyTxVL2m+joc3spptLnOyfh0EVrMKcvy7T57yRBRVH1wRBawRjK/TYuCWqy7mQ++5hRjFJmUefPxFvvSNuzky4sLJUT7Lp+5GXU7xPJqnGss/r7mZOKhE+QfQkPleQoSGeodqCN03hFx7Ew8WFq+T0NieJ3eqz1+TEzn05Dp9qL1DJJwGUMfywrbdPPHSTqrqKZcMV19xMeWWBM2PKlxz0VKWXrCUKCkyVHX8cMMTDFQ9WX6aq/hTD/ST8eR0YCofT9AKE2gm59TrrCHX/Rp9GxroxI2k49EfAIo1wQEnSDIlNkp3S8SP3XY1t99yOZpWcCbimz+4l7sf2kjFTUjUcUKd8HGDLqnjpG8MON/4beKSkITQm4SKF14+eIjUOUQ9Xe2tRGhulWBcPWkgHyb5vQLpdbwtToC8iOCrofjM4bEMjjnuuP8xhmopXjwLF89n3uKFHKt69o86Do1kZLbAFZdfBbaAt2WeeGEHW3YdourC7HFK4pwFTOXjuVCnMwLVYA0RFLEGNROhPsHG4Zjb6viXP3Yjl164mGplBG8Sdh04isTF4Pt8Ep40MJVM4bbh4MupA05VqKswksHmnft54aUdOA3OT6suOI+ylXyBRQhPOtEIUvC5pSdn9HGH9sSQb3zOkDnDrr1HeeixF0gdQMSRIwP84f/6Iv/u03/ML/325/g3v/2n/Mqn/5i77r6fNBPGUsuBYyP84N5HGKl6nBfUvTo142zilGSeyv43RTK/XuS2VzEhw2iwGTdknKdFRlk2r4VP/MQHWLhgDi7YJsgwmCh4sJ0MOv5fmM4br3r1IRF30wwSbDMGb2KODozw1W9/nyMDw2QKM3u6Wbd6FaXGqZdAFuR0o9CGrpCXpajPp9dGBY5H6EldJIhYRkdT7r3vUQaGM1xqUWcZHEx55sUDbNzcy2ObB9m4eYAnX+xj2449ZF5Qk+BNiQ0bn2HXnv04n+ekfuUdzyqm8vGUZJ6qlzRfx8Op3p+KxqCY+vnwdzTu4xs0jeDbq6rB11gnIrmlyYNqvEwiRA3Gh7KchCPOjBosBhtFREZZf9ESPvnjtzC7MEKbGUVdDeIW1BYgdy7SJn+shpVC8kxLmcSIjSkYwXpP3Vv6tZW+TBhMUwbTlP7Us7/ieHTnIT77ha9yx1NbKMZFSjrEzVcvY9HcLtQkwRNNND+t1mA0HPkQSB7hJA67kz5DXYaoosZibBw2VcTnHm7NVPOoCBWJ2d07yh0bnqZiWynaDJMNUWKUguunxYxQsqMU7RiFqEK3rdKSDRKlIzjv2TdY5c6NzzFUd2QEm/ibial8PCWZ31w0RFHYWfMuw7t6kHGnzH0sIBYrUThKVwmO8T7oj4KAKWCjmKJx3Hr1Rfyz299B2Q1Skjr1ykg+QCZm87xkyGVScE8I+ecEsHlQrEjE489t5bf+x5f5ld/7G371s1/gVz/7v/nVz3yBX/mdP+eOhzYxVCug1SpXXLSYj3zgBtpKUThDQAwqPo8eD6kPGhs23inOhw0Poy7kS8aHRWDjECCCkXm8vrlEd0aoKjz+/GaODoySepjbYfi1/+sn+K+/9nP83m/8LL//6z/DZ3/jk3zm13+G3/2Nn+N3f/WTfPY3PsWH3n01sc0Yq2Xcv/E5dh7oI819r88lnONkVgSHJSOmRuzHiDREVKtmJ1mUNRCM/MZnxFqjZFIKppFth/Ht30igtRDxkdvfzW3XX04xHaQ7rhH5asjj7F1jajiuHisKOIemVWJSTDbG0X07+O79z/L1+17i6/dt4Zv3b+LuRzZz8PAI9cExuuOYW6+5nF/5pU9x3ryZJCZPhD6uwpkmZ55gljDGhmxNrk7k6xQ0JdI64lO8D/mmmwmWB7iMv9bb28vDD9yLcRWKpKxdMoMP3Hgpt165nHdfs4bbrl7De666mPdcvZr3XLWCm65ezjuvW84Hb72Shd1FSsaxd8cennx8E/W0OFWPedNxjpPZI+IpWKU9cbTFNdoiRyzBT2HCR/KVUA1puQwavh9ndER1iiYDwsHpPt8pK1hDa2yZ3Vbgkx+9natXLaCLQdqTkOpLCB5swRcil8pN6gzqEc0QVyN2FeJ0mFapY/0wMILKGF5GETPCjLaMGy5fzL//5Hv51V/8F1x0/lxaE7A+tysLE+KUEK/YeM25DDxYV6csGYkbJXaVMBvktZpYE+S/5Uz2XtmzcweH9+6i4MeY3WL40XdeQ09JaTMpZalT0holrdKidVp8RgtVWjXlwoU9XLJsHm2mjnEVnn7mSY70DjSa+pzBG3bOb9Z1T9eisFGmwZEp7Dk2wsNPbaLmoL0Uc8nKJSyZ1UFso0mhOzrlrD1Rx0hNefylvew82EskygXzZ7JuxWJKNh8QwcMz+HF4QyVVdrx8kL0HDjGzZwarl51HOSJPLWCCRUQhHPtuwsJLldHUc++jT7P7UD9ebCCTVFADakI9W8tFFs7pYcncHmZ1tVKOyiFeXFLEe4zEYaNDQAnhWGE4hrzP6h1eYvb3jfLAE89RqRraS4Zr1y1j7sy28cN+hIYqFWSVx5M6x/bd+3hx+8tUMkuxrYtr1y1mZlsLCXl8ZeOMehVEw7N5hbFU2LznABuf24KxhgUzO7j0wmXM7mzFmBMbA6aug070udOFN0zmMwVVBU1DhnYiavkB8FHu2JNIfTwJYvN3JpHZp6RqGRNLlh+KHgvERonEhy1rafgxhMshZLm3mtdwJFosDpNnJPW5pLYayBzswkqmQsUb6rl+bYBWV8XgcTbGSUTmPcUkD0TVkAJBxCOS5fI05OEIVXHhMxichOBQUUeWOepqcfnBQzGQ4DEmQ2wIuBUUqyFYFQEvSuY8jnBUBkQYCyYOd4xz4e9zXVsAG44XQBWc91SBugTfk8SkxJKSaLFJLXrzcc6RudkqgWaQ+/lm3qPiMERYEawJJGpewzaTWURA6ygRtTzbZaQe70Oyv7gprX0gSl5GWPuHjtUQ7xYRHPdDZtBAVKshO6g04u2QkEClQQaFyOWFysS9lGCYMOF8nZCudDz97EQIGISE6SoWl79uXJZLa4sTg883RCwZGI8zERr86LDeBXcpkXDshQaiqnPEErKpVm2Q3bHmQbR5/ayGamUayje5haSuijdgyLCSYbTUVN8zL3lPhTesMzdG5ul8kImyBELyWQoWikZJJAT7q89dGk8GVdQHN0ib+2XE4kKUdp4UJiSGMXlT5BaS/PbWhCv8PbEr2IxQ1WBFjtBcUioRKS4S0khIrcOZGs5UUakiUYYan8f6Nbwmgh/F5EcKu4iN10JYfxg8kQQSRvm6IvjTTcVEaUYEk89Khgx8lYiUKD+dILRCfmmwd7sINAasQ4yjYIWCWBJiIl+Y1O9TVQqmcON08uNEOOck8yTkFoRAsCAzA+ly6S3h/ROhITG92NyA5vJpPHeuzEk6bjTQcUeKPON9fjpqPvlOuO0zvuBqEDl8KsgGIdjzMtNIFhOSNE4IaBl3Tw1VaJSV10UIi18NuS9UcrdO8lzTeRkBGi4hUFJCrKJB8yXgxCAM3823zFXxjeOZ8yInlayQmSDlg7qjqDYGfTABjod1NZF50sw4Bccj/OnEuU3m46C5kc5040zj9eF4ROYs9NcbVjPONvQ17jBO4+ziREQ+G3jLkXka5y7eTCLzetSM6Wl+GucKpg6eack8jbcNpsk8jbcNpsk8jbcNpsl8FnGmNxHOZNlvBUyT+W2Kf4qEfs3WjGm8fkwl2Om2Bp3p8s91TEvms4jmDZ9/akQ7G5iWzNN422BaMk/jbYNpMk/jbYNpMk/jbYNpMk/jbYNpMk/jbYNpMk/jbYNpMk/jbYM3bGd+q/s3n6r+p3p/GifGmW67qeVPS+ZpnBVM3Wo/3RCRack8jbcupg6Qack8jbcspvq6vOXI3Oyz23xNYxpvOTJPYxonwv8PkZ0+EswujPkAAAAASUVORK5CYII='

ROOT = Path.home() / 'PDF_Studio_Pro_Data'
FIELDS = ['Legal Name','Trade Name','Registered Address','City','State','State Code','GSTIN','Contact Person','Phone','Email','Website']
STATES = {'01':'Jammu and Kashmir','02':'Himachal Pradesh','03':'Punjab','04':'Chandigarh','05':'Uttarakhand','06':'Haryana','07':'Delhi','08':'Rajasthan','09':'Uttar Pradesh','10':'Bihar','11':'Sikkim','12':'Arunachal Pradesh','13':'Nagaland','14':'Manipur','15':'Mizoram','16':'Tripura','17':'Meghalaya','18':'Assam','19':'West Bengal','20':'Jharkhand','21':'Odisha','22':'Chhattisgarh','23':'Madhya Pradesh','24':'Gujarat','26':'Dadra and Nagar Haveli and Daman and Diu','27':'Maharashtra','29':'Karnataka','30':'Goa','31':'Lakshadweep','32':'Kerala','33':'Tamil Nadu','34':'Puducherry','35':'Andaman and Nicobar Islands','36':'Telangana','37':'Andhra Pradesh','38':'Ladakh'}
DEFAULTS = {'Firm':'Akshay Devpura & Associates','Address':'B 134 Divine Heritage, Jesal Park, Bhayandar East','Email':'caakshaydevpura@gmail.com','Phone':'+91 8976666748','GSTIN':'','Bank':'Karnataka Bank Ltd','Branch':'Bhayandar East','Beneficiary':'Akshay Devpura and Associates','Account':'1062500100XXXXXX','IFSC':'KARB0000XXX','Logo':'','Signature / stamp':'','Terms':'Payment due on receipt.','GST registered':'Yes'}
def money(v): return Decimal(str(v)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
def totals(items, state, rate='18'):
    net = sum((money(x['amount']) for x in items), Decimal('0.00'))
    half = money(net * Decimal(str(rate)) / 200)
    cg, sg, ig = (half,half,Decimal('0.00')) if state == '27' else (Decimal('0.00'),Decimal('0.00'),money(net*Decimal(str(rate))/100))
    return dict(net=str(net),cgst=str(cg),sgst=str(sg),igst=str(ig),total=str(net+cg+sg+ig))
def fy_for(d):
    y=d.year if d.month >=4 else d.year-1
    return f'{y}-{y+1}'
def words(value):
    small='Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen'.split()
    tens=['','','Twenty','Thirty','Forty','Fifty','Sixty','Seventy','Eighty','Ninety']
    def w(n):
        if n<20:return small[n]
        if n<100:return tens[n//10]+(' '+w(n%10) if n%10 else '')
        for unit,label in [(10000000,'Crore'),(100000,'Lakh'),(1000,'Thousand'),(100,'Hundred')]:
            if n>=unit:return w(n//unit)+' '+label+(' '+w(n%unit) if n%unit else '')
    n=int(money(value)*100)
    return 'Indian Rupees '+w(n//100)+(' and '+w(n%100)+' Paise' if n%100 else '')+' Only'
class Store:
    def __init__(self, folder=ROOT):
        folder.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(folder/'invoices.sqlite3'))
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY, data TEXT NOT NULL); CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT); CREATE TABLE IF NOT EXISTS years(fy TEXT PRIMARY KEY,seq INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY,number TEXT UNIQUE,fy TEXT,data TEXT NOT NULL,deleted INTEGER NOT NULL DEFAULT 0);')
        for y in ['2025-2026','2026-2027',fy_for(date.today())]:self.db.execute('INSERT OR IGNORE INTO years(fy) VALUES(?)',(y,))
        self.db.executescript('CREATE TABLE IF NOT EXISTS payments(invoice_id INTEGER PRIMARY KEY, paid INTEGER NOT NULL DEFAULT 0, payment_date TEXT); CREATE TABLE IF NOT EXISTS payment_history(id INTEGER PRIMARY KEY, invoice_id INTEGER, action TEXT, payment_date TEXT, changed_at TEXT DEFAULT CURRENT_TIMESTAMP);')
        self.db.commit()
    def settings(self):
        data={**DEFAULTS,**dict(self.db.execute('SELECT k,v FROM settings'))}
        if not data.get('Logo') or Path(data['Logo']).name=='icai_ca_india.png':data['Logo']=DEFAULTS['Logo']
        return data
    def clients(self):return [(i,json.loads(d)) for i,d in self.db.execute('SELECT id,data FROM clients ORDER BY id')]
    def save_client(self,d,i=None):
        with self.db:
            if i:self.db.execute('UPDATE clients SET data=? WHERE id=?',(json.dumps(d),i))
            else:i=self.db.execute('INSERT INTO clients(data) VALUES(?)',(json.dumps(d),)).lastrowid
        return i
    @staticmethod
    def client_key(c):
        gst=c.get('GSTIN','').strip().upper()
        if gst:return 'GSTIN:'+gst
        return 'NAME:'+json.dumps([c.get(k,'').strip().casefold() for k in ('Legal Name','Registered Address','City')])
    def set_paid(self, invoice_id, paid, payment_date=None):
        row=self.db.execute('SELECT data FROM invoices WHERE id=? AND deleted=0',(invoice_id,)).fetchone()
        if not row:raise ValueError('Active invoice not found.')
        if paid:
            dt=date.fromisoformat(payment_date)
            if dt<date.fromisoformat(json.loads(row[0])['date']) or dt>date.today():
                raise ValueError('Payment date must be between the invoice date and today.')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO payments(invoice_id,paid,payment_date) VALUES(?,?,?)',(invoice_id,int(bool(paid)),payment_date if paid else None))
            self.db.execute('INSERT INTO payment_history(invoice_id,action,payment_date) VALUES(?,?,?)',(invoice_id,'Paid' if paid else 'Unpaid',payment_date if paid else None))
    def report(self, fy, client_key=None):
        rows=[];net=Decimal('0');gross=Decimal('0');received=Decimal('0');paid_net=Decimal('0')
        for i,raw,paid,payment_date in self.db.execute('SELECT i.id,i.data,COALESCE(p.paid,0),p.payment_date FROM invoices i LEFT JOIN payments p ON p.invoice_id=i.id WHERE i.deleted=0 AND i.fy=? ORDER BY i.id',(fy,)):
            d=json.loads(raw)
            if client_key and self.client_key(d['client'])!=client_key:continue
            n=Decimal(d['totals']['net']);g=Decimal(d['totals']['total']);net+=n;gross+=g
            if paid:received+=g;paid_net+=n
            rows.append((i,d,bool(paid),payment_date))
        return dict(rows=rows,net=net,gross=gross,received=received,outstanding=gross-received,paid_net=paid_net)
    def next_number(self, fy):
        row=self.db.execute('SELECT seq FROM years WHERE fy=?',(fy,)).fetchone()
        if row is None:raise ValueError('Unknown financial year')
        seq=row[0]
        # Include historical records and deleted numbers when detecting the high-water mark.
        for number, in self.db.execute('SELECT number FROM invoices WHERE fy=?',(fy,)):
            match=re.fullmatch(re.escape(fy)+r'/([0-9]+)',number)
            if match:seq=max(seq,int(match[1]))
        return f'{fy}/{seq+1:02d}'
    def validate_number(self, number):
        number=number.strip()
        if not re.fullmatch(r'[A-Za-z0-9/-]{1,16}',number):
            raise ValueError('Invoice number must be 1–16 characters: letters, digits, / or - only.')
        if self.db.execute('SELECT 1 FROM invoices WHERE number=? COLLATE NOCASE',(number,)).fetchone():
            raise ValueError('Invoice number already exists or was deleted. Choose a different number.')
        return number
    def issue(self,d):
        try:
            self.db.execute('BEGIN IMMEDIATE')
            number=self.validate_number(d.get('number') or self.next_number(d['fy']))
            row=self.db.execute('SELECT seq FROM years WHERE fy=?',(d['fy'],)).fetchone()
            if row is None:raise ValueError('Unknown financial year')
            match=re.fullmatch(re.escape(d['fy'])+r'/([0-9]+)',number)
            seq=max(row[0],int(match[1])) if match else row[0]
            d={**d,'number':number}
            self.db.execute('UPDATE years SET seq=? WHERE fy=?',(seq,d['fy']))
            self.db.execute('INSERT INTO invoices(number,fy,data) VALUES(?,?,?)',(number,d['fy'],json.dumps(d)))
            self.db.commit(); return d
        except Exception:self.db.rollback();raise

# PIN protects entry to the application; the local database is not encrypted.
class PinSecurity:
    def __init__(self, folder=None):
        self.path = (folder or ROOT) / 'security.json'
    def read(self):
        if not self.path.exists(): return None
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if not all(k in data for k in ('salt', 'hash', 'failures', 'until')):
            raise ValueError('Security file is damaged. Restore it from your backup.')
        return data
    def write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data), encoding='utf-8')
        try: temporary.chmod(0o600)
        except OSError: pass
        temporary.replace(self.path)
    def set_pin(self, pin):
        if not re.fullmatch(r'[0-9]{4}', pin): raise ValueError('Enter exactly four digits (0–9).')
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac('sha256', pin.encode(), bytes.fromhex(salt), 300000).hex()
        self.write(dict(salt=salt, hash=digest, failures=0, until=0))
    def remaining(self):
        d=self.read()
        return max(0, int(d['until']-time.time()+0.999)) if d else 0
    def verify(self, pin):
        d=self.read()
        if not d or self.remaining(): return False
        candidate=hashlib.pbkdf2_hmac('sha256', pin.encode(), bytes.fromhex(d['salt']), 300000).hex()
        valid=hmac.compare_digest(candidate,d['hash'])
        if valid: d['failures']=0; d['until']=0
        else:
            d['failures']+=1
            if d['failures']>=5: d['until']=time.time()+60; d['failures']=0
        self.write(d)
        return valid

def install():
    for module,package in [('PyQt6','PyQt6'),('openpyxl','openpyxl'),('PIL','Pillow'),('reportlab','reportlab')]:
        if importlib.util.find_spec(module) is None:
            print('Installing',package,'— internet is required on first launch.')
            subprocess.check_call([sys.executable,'-m','pip','install',package])

def export_professional_pdf(d, path):
    """Print-ready A4 invoice. Wrapped rows and repeating headings support long invoices."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image, KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab
    fonts=Path(reportlab.__file__).parent / "fonts"
    if "InvoiceSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("InvoiceSans",str(fonts/"Vera.ttf")))
        pdfmetrics.registerFont(TTFont("InvoiceSansBold",str(fonts/"VeraBd.ttf")))
    s=d['firm'];c=d['client'];t=d['totals'];blue=colors.HexColor('#173e70');pale=colors.HexColor('#edf3fa');line=colors.HexColor('#c6d3e2')
    width=A4[0]-84
    normal=ParagraphStyle('body',fontName='InvoiceSans',fontSize=9,leading=13,textColor=colors.HexColor('#243750'),spaceAfter=0)
    def P(text, bold=False, size=9, align=TA_LEFT, color=None):
        style=ParagraphStyle('cell',parent=normal,fontName='InvoiceSansBold' if bold else 'InvoiceSans',fontSize=size,leading=size+4,alignment=align,textColor=color or normal.textColor)
        return Paragraph(escape(str(text)).replace('\n','<br/>'),style)
    def image(path,w,h):
        if not path or not Path(path).is_file():return Spacer(w,h)
        iw,ih=ImageReader(path).getSize();scale=min(w/iw,h/ih)
        return Image(path,width=iw*scale,height=ih*scale)
    def table(rows,widths,extra=()):
        tab=Table(rows,colWidths=widths,hAlign='LEFT')
        tab.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]+list(extra)))
        return tab
    logo=s.get('Logo')
    if not logo or not Path(logo).exists():logo=str(ROOT/'assets'/'attached_ca_india.png')
    firm=[P(s['Firm'],True,18,color=blue),Spacer(1,4),P('CHARTERED ACCOUNTANTS',True,9,color=blue),Spacer(1,7),P(s['Address']),P('Email: '+s['Email']+'  |  Tel: '+s['Phone']),P('GSTIN: '+(s['GSTIN'] or 'Unregistered'))]
    header=table([[image(logo,67,66),firm]],[85,width-85],[('LEFTPADDING',(0,0),(0,0),0),('RIGHTPADDING',(1,0),(1,0),0),('LINEBELOW',(0,0),(-1,0),1.4,blue)])
    title='TAX INVOICE' if s['GST registered']=='Yes' else 'INVOICE'
    story=[header,Spacer(1,12),table([[P(title,True,15,color=blue),P('ORIGINAL FOR RECIPIENT',False,8,TA_RIGHT)]],[width*.6,width*.4]),Spacer(1,9)]
    bill=[P('BILL TO',True,9,color=blue),Spacer(1,5),P(c['Legal Name'],True,11)]
    for k in ['Trade Name','Registered Address','City']:
        if c.get(k):bill.append(P(c[k]))
    bill += [P(c.get('State','')+' - '+c.get('State Code','')),P('GSTIN: '+(c.get('GSTIN') or 'Unregistered'))]
    for text in [c.get('Contact Person',''),c.get('Phone',''),c.get('Email',''),c.get('Website','')]:
        if text:bill.append(P(text))
    meta=[['Invoice No.',d['number']],['Invoice Date',date.fromisoformat(d['date']).strftime('%d %B %Y')],['Financial Year',d['fy']],['Place of Supply',d['pos']+' - '+STATES.get(d['pos'],'')],['Supply Type','Intra-state' if d['pos']=='27' else 'Inter-state'],['Reverse Charge','No']]
    metadata=table([[P(k,True,8),P(v,False,9)] for k,v in meta],[83,width*.46-103],[('LEFTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),4)])
    story += [table([[bill,metadata]],[width*.54,width*.46],[('BOX',(0,0),(-1,-1),.6,line),('BACKGROUND',(0,0),(-1,-1),pale),('LINEAFTER',(0,0),(0,0),.6,line)]),Spacer(1,12)]
    rows=[[P('#',True,9,color=colors.white),P('Description of professional services',True,9,color=colors.white),P('SAC',True,9,color=colors.white),P('Net Amount\n(INR)',True,9,TA_RIGHT,colors.white)]]
    for i,x in enumerate(d['items'],1):rows.append([P(i),P(x['description']),P(x['sac']),P(f"{Decimal(x['amount']):,.2f}",align=TA_RIGHT)])
    services=table(rows,[30,width-179,59,90],[('BACKGROUND',(0,0),(-1,0),blue),('LINEBELOW',(0,0),(-1,0),.5,blue),('LINEBELOW',(0,1),(-1,-1),.4,line),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f7f9fc')]),('TOPPADDING',(0,1),(-1,-1),4),('BOTTOMPADDING',(0,1),(-1,-1),4)])
    services.repeatRows=1;story += [services,Spacer(1,12)]
    rate=Decimal(d['rate']);taxlabels=[('net','Net professional fees'),('cgst',f'CGST @ {rate/2:g}%'),('sgst',f'SGST @ {rate/2:g}%'),('igst',f'IGST @ {rate:g}%'),('total','TOTAL PAYABLE (INR)')]
    summary=table([[P(label,True if k=='total' else False,9,color=blue),P(f'{Decimal(t[k]):,.2f}',k=='total',10,TA_RIGHT,blue)] for k,label in taxlabels if k in ('net','total') or (k in ('cgst','sgst') if d['pos']=='27' else k=='igst')],[width*.56-90,90],[('BACKGROUND',(0,-1),(-1,-1),pale),('LINEABOVE',(0,-1),(-1,-1),1,blue),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)])
    amount_words=[P('AMOUNT IN WORDS',True,9,color=blue),Spacer(1,7),P(words(t['total']),size=10)]
    summary_block=table([[amount_words,summary]],[width*.44,width*.56],[('LEFTPADDING',(1,0),(1,0),0),('RIGHTPADDING',(1,0),(1,0),0)])
    story += [KeepTogether([summary_block]),Spacer(1,12)]
    bank=[P('BANK DETAILS',True,10,color=blue),Spacer(1,7)]
    for key,label in [('Bank','Bank'),('Branch','Branch'),('Beneficiary','Beneficiary'),('Account','Account No.'),('IFSC','IFSC Code')]:bank += [P(label+': '+s[key])]
    sign=[P('For '+s['Firm'],True,10,TA_CENTER,blue),Spacer(1,9),image(s.get('Signature / stamp'),140,38),Spacer(1,8),P('Authorised Signatory',True,9,TA_CENTER)]
    bottom=table([[bank,sign]],[width*.55,width*.45],[('BOX',(0,0),(-1,-1),.6,line),('LINEAFTER',(0,0),(0,0),.6,line),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)])
    story += [KeepTogether([bottom])]
    if s.get('Terms'):story += [Spacer(1,5),P('Terms: '+s['Terms'],size=8)]
    def footer(canvas,doc):
        canvas.saveState();canvas.setStrokeColor(line);canvas.line(42,34,A4[0]-42,34);canvas.setFont('InvoiceSans',8);canvas.setFillColor(blue);canvas.drawString(42,22,d['number']);canvas.drawRightString(A4[0]-42,22,f'Page {doc.page}');canvas.restoreState()
    SimpleDocTemplate(str(path),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=28,bottomMargin=40,title=title+' '+d['number'],author=s['Firm']).build(story,onFirstPage=footer,onLaterPages=footer)

def run():
    install()
    ROOT.mkdir(parents=True, exist_ok=True)
    logo = ROOT / 'assets' / 'attached_ca_india.png'
    logo.parent.mkdir(exist_ok=True)
    if not logo.exists(): logo.write_bytes(base64.b64decode(EMBEDDED_CA_LOGO))
    DEFAULTS['Logo'] = str(logo)
    from PyQt6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QComboBox,QPushButton,QTabWidget,QTableWidget,QTableWidgetItem,QMessageBox,QFileDialog,QDateEdit,QLabel,QTextBrowser,QDialog,QDialogButtonBox,QInputDialog,QHeaderView,QScrollArea
    from PyQt6.QtCore import QDate,Qt,QMarginsF,QRegularExpression
    from PyQt6.QtGui import QTextDocument,QPageSize,QPdfWriter,QPainter,QColor,QPixmap,QRegularExpressionValidator
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.drawing.image import Image as XLImage
    security=PinSecurity()
    class PinDialog(QDialog):
        def __init__(self, setup=False, parent=None):
            super().__init__(parent); self.setup=setup
            self.setWindowTitle('Invoice creation Utility | '+('Create PIN' if setup else 'Unlock'))
            self.setFixedWidth(440)
            layout=QVBoxLayout(self);layout.setContentsMargins(30,26,30,26);layout.setSpacing(15)
            mark=QLabel();mark.setPixmap(QPixmap(str(logo)).scaled(100,85,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));layout.addWidget(mark,alignment=Qt.AlignmentFlag.AlignCenter)
            title=QLabel('Secure your workspace' if setup else 'Welcome back, Akshay');title.setObjectName('title');layout.addWidget(title)
            layout.addWidget(QLabel('Create a 4-digit PIN to open this utility.' if setup else 'Enter your 4-digit PIN to continue.'))
            self.pin=QLineEdit();self.pin.setPlaceholderText('4-digit PIN');self.pin.setEchoMode(QLineEdit.EchoMode.Password);self.pin.setMaxLength(4);self.pin.setValidator(QRegularExpressionValidator(QRegularExpression('[0-9]{0,4}')));layout.addWidget(self.pin)
            self.confirm=None
            if setup:
                self.confirm=QLineEdit();self.confirm.setPlaceholderText('Confirm PIN');self.confirm.setEchoMode(QLineEdit.EchoMode.Password);self.confirm.setMaxLength(4);self.confirm.setValidator(QRegularExpressionValidator(QRegularExpression('[0-9]{0,4}')));layout.addWidget(self.confirm)
            self.message=QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
            button('Save PIN' if setup else 'Unlock',self.submit,layout)
            self.pin.returnPressed.connect(self.submit)
            if self.confirm:self.confirm.returnPressed.connect(self.submit)
            note=QLabel('PIN controls access to this application. Local files are not encrypted. Keep your PIN safe; there is no built-in reset.');note.setWordWrap(True);note.setObjectName('muted');layout.addWidget(note)
        def submit(self):
            try:
                if not re.fullmatch(r'[0-9]{4}',self.pin.text()):raise ValueError('Enter exactly four digits.')
                if self.setup:
                    if self.pin.text()!=self.confirm.text():raise ValueError('PINs do not match.')
                    security.set_pin(self.pin.text())
                else:
                    seconds=security.remaining()
                    if seconds:raise ValueError(f'Too many attempts. Try again in {seconds} seconds.')
                    if not security.verify(self.pin.text()):raise ValueError('Incorrect PIN. After five failures, access pauses for 60 seconds.')
                self.accept()
            except Exception as e:self.message.setText(str(e));self.pin.clear()
    def alert(parent,text):QMessageBox.information(parent,'Invoice creation Utility',str(text))
    def button(text,fn,layout):
        b=QPushButton(text);b.clicked.connect(fn);layout.addWidget(b);return b
    def image_html(path,width):
        if path and Path(path).is_file():
            # Qt rich text reliably resolves local images and keeps aspect ratio.
            return f'<img src="{escape(Path(path).resolve().as_uri(),quote=True)}" width="{width}">'
        return ''
    def html(d):
        s=d['firm'].copy();s['Logo']=s.get('Logo') if s.get('Logo') and Path(s['Logo']).exists() else str(logo);c=d['client'];t=d['totals'];e=lambda v:escape(str(v)).replace('\n','<br>')
        row=''.join(f"<tr><td>{i+1}</td><td>{e(x['description'])}</td><td>{e(x['sac'])}</td><td align='right'>{e(x['amount'])}</td></tr>" for i,x in enumerate(d['items']))
        title='TAX INVOICE' if s['GST registered']=='Yes' else 'INVOICE'
        taxrows=''.join(f"<tr><td>{label}</td><td align='right'>{t[key]}</td></tr>" for key,label in [('net','Professional fees (net)'),('cgst',f"CGST {Decimal(d['rate'])/2}%"),('sgst',f"SGST {Decimal(d['rate'])/2}%"),('igst',f"IGST {d['rate']}%"),('total','TOTAL INR')])
        details='<br>'.join(e(c.get(k,'')) for k in ['Legal Name','Trade Name','Registered Address','City'] if c.get(k))
        return f"""<html><head><style>body{{font-family:Arial;font-size:10pt;color:#203a34}} h1{{color:#175ea8;font-size:19pt}} h2{{color:#db7b20}} th{{background:#175ea8;color:white}} td,th{{padding:7px}} table{{border-collapse:collapse}} </style></head><body>
        <table width='100%'><tr><td>{image_html(s['Logo'],90)}</td><td><h1>{e(s['Firm'])}</h1>{e(s['Address'])}<br>Email: {e(s['Email'])} | Tel: {e(s['Phone'])}<br>GSTIN: {e(s['GSTIN']) or 'Unregistered'}</td></tr></table>
        <h2>{title}</h2><b>Invoice No: {e(d['number'])}</b> &nbsp; Date: {e(d['date'])}<br>Financial Year: {e(d['fy'])} | Original for Recipient
        <hr><b>BILL TO</b><p>{details}<br>State: {e(c['State'])} ({e(c['State Code'])})<br>GSTIN: {e(c['GSTIN']) or 'Unregistered'}<br>Contact: {e(c['Contact Person'])} | {e(c['Phone'])}<br>{e(c['Email'])} | {e(c['Website'])}</p>
        <b>Place of supply:</b> {e(d['pos'])} - {e(STATES.get(d['pos'],''))}<br>Supply: {'Intra-state' if d['pos']=='27' else 'Inter-state'} | Reverse charge: No
        <p><table border='1' cellspacing='0' width='100%'><tr><th>No.</th><th>Description of professional services</th><th>SAC</th><th>Net INR</th></tr>{row}</table></p>
        <table width='100%' border='1'>{taxrows}</table><p><b>Amount in words:</b> {e(words(t['total']))}</p>
        <hr><b>BANK DETAILS</b><br>Bank: {e(s['Bank'])} | Branch: {e(s['Branch'])}<br>Beneficiary: {e(s['Beneficiary'])}<br>Account No: {e(s['Account'])} | IFSC: {e(s['IFSC'])}
        <p>{e(s['Terms'])}</p><p align='right'>For {e(s['Firm'])}<br>{image_html(s['Signature / stamp'],145)}<br>Authorised Signatory</p></body></html>"""
    class Chart(QWidget):
        def __init__(self):super().__init__();self.values=[Decimal(0)]*12;self.setMinimumHeight(290)
        def paintEvent(self,event):
            p=QPainter(self);p.fillRect(self.rect(),QColor('white'));p.setPen(QColor('#173e70'));p.drawText(15,25,'Monthly invoice total (INR, including GST) — April to March')
            maximum=max(self.values) or Decimal(1);width=max(20,(self.width()-90)//12);height=self.height()-100
            for i,v in enumerate(self.values):
                x=55+i*width;h=int(v/maximum*height);p.fillRect(x,55+height-h,width-12,h,QColor('#327ac1'));p.drawText(x,78+height,['Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec','Jan','Feb','Mar'][i]);p.drawText(x,48+height-h,f'{v:,.0f}')
            p.end()
    class App(QMainWindow):
        def __init__(self):
            super().__init__();self.store=Store();self.current=None;self.client_id=None;self.setWindowTitle('Invoice creation Utility');self.resize(1250,850)
            shell=QWidget();outer=QVBoxLayout(shell);outer.setContentsMargins(22,16,22,16);outer.setSpacing(16)
            banner=QWidget();banner.setObjectName('banner');b=QHBoxLayout(banner);b.setContentsMargins(20,12,20,12)
            brand=QLabel();brand.setPixmap(QPixmap(str(logo)).scaled(86,72,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));b.addWidget(brand)
            heading=QVBoxLayout();title=QLabel('Invoice creation Utility');title.setObjectName('brandTitle');heading.addWidget(title);subtitle=QLabel('AKSHAY DEVPURA & ASSOCIATES  •  PROFESSIONAL BILLING');subtitle.setObjectName('muted');heading.addWidget(subtitle);b.addLayout(heading);b.addStretch()
            button('Lock Workspace',self.lock_workspace,b);outer.addWidget(banner)
            self.tabs=QTabWidget();outer.addWidget(self.tabs);self.setCentralWidget(shell)
            self.invoice_tab();self.directory_tab();self.register_tab();self.settings_tab();self.refresh()
            self.statusBar().showMessage(f'Local database: {ROOT} | Back up regularly')
        def lock_workspace(self):
            self.hide()
            if PinDialog().exec()==QDialog.DialogCode.Accepted:self.show()
            else:self.close()
        def change_pin(self):
            if PinDialog(parent=self).exec()==QDialog.DialogCode.Accepted:
                if PinDialog(setup=True,parent=self).exec()==QDialog.DialogCode.Accepted:alert(self,'PIN changed successfully.')
        def page(self,title):
            w=QWidget();layout=QVBoxLayout(w);layout.setContentsMargins(20,20,20,20);layout.setSpacing(12);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(w);self.tabs.addTab(scroll,title);return layout
        def year_combo(self):
            c=QComboBox();c.addItems([r[0] for r in self.store.db.execute('SELECT fy FROM years ORDER BY fy')]);c.setCurrentText(fy_for(date.today()));return c
        def invoice_tab(self):
            l=self.page('Create Invoice');head=QLabel('Akshay Devpura & Associates  |  Invoice Workspace');head.setObjectName('title');l.addWidget(head)
            bar=QHBoxLayout();l.addLayout(bar);self.fy=self.year_combo();bar.addWidget(QLabel('Financial year'));bar.addWidget(self.fy);button('+ Financial Year',self.add_year,bar)
            self.dt=QDateEdit(QDate.currentDate());self.dt.setCalendarPopup(True);self.dt.setDisplayFormat('dd-MM-yyyy');bar.addWidget(self.dt);self.dt.dateChanged.connect(lambda:self.fy.setCurrentText(fy_for(self.dt.date().toPyDate())))
            number_bar=QHBoxLayout();l.addLayout(number_bar);number_bar.addWidget(QLabel('Invoice Number'))
            self.invoice_number=QLineEdit();self.invoice_number.setMaxLength(16);self.invoice_number.setToolTip('Automatically suggested for the selected FY. You may edit before issuing. Maximum 16 characters: letters, digits, / or -.');number_bar.addWidget(self.invoice_number)
            button('Use Next Number',self.suggest_number,number_bar);self.fy.currentTextChanged.connect(self.suggest_number);self.suggest_number()
            hint=QLabel('Edit the suggested number if needed. Duplicate and deleted numbers cannot be reused.');hint.setObjectName('muted');l.addWidget(hint)
            self.quick=QComboBox();l.addWidget(self.quick);self.quick.currentIndexChanged.connect(self.fill_client)
            self.client_inputs={};grid=QHBoxLayout();l.addLayout(grid);left=QFormLayout();right=QFormLayout();grid.addLayout(left);grid.addLayout(right)
            for i,k in enumerate(FIELDS):
                self.client_inputs[k]=QLineEdit();(left if i<6 else right).addRow(k,self.client_inputs[k])
            self.client_inputs['GSTIN'].textChanged.connect(self.detect_state)
            controls=QHBoxLayout();l.addLayout(controls);button('Save Client',self.save_client,controls);button('New Client',self.new_client,controls)
            self.pos=QComboBox()
            for k,v in STATES.items():self.pos.addItem(k+' - '+v,k)
            self.pos.setCurrentIndex(self.pos.findData('27'));controls.addWidget(QLabel('Place of supply'));controls.addWidget(self.pos)
            self.rate=QComboBox();self.rate.addItems(['18','0','5','12','28','40']);controls.addWidget(QLabel('GST %'));controls.addWidget(self.rate)
            self.items=QTableWidget(0,3);self.items.setAlternatingRowColors(True);self.items.setMinimumHeight(180);self.items.setHorizontalHeaderLabels(['Description of services','SAC','Net amount INR']);self.items.setColumnWidth(1,140);self.items.setColumnWidth(2,180);self.items.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);l.addWidget(self.items)
            buttons=QHBoxLayout();l.addLayout(buttons);button('+ Service',self.add_item,buttons);button('Remove selected service',self.remove_item,buttons)
            self.summary=QLabel();self.summary.setStyleSheet('background:#eaf2fc;color:#163e70;padding:16px;border-radius:8px;font-size:12pt;font-weight:600;');self.summary.setWordWrap(True);l.addWidget(self.summary);self.items.itemChanged.connect(self.recalculate);self.rate.currentTextChanged.connect(self.recalculate);self.pos.currentIndexChanged.connect(self.recalculate)
            actions=QHBoxLayout();l.addLayout(actions);button('Preview Draft',self.preview_draft,actions);button('Save / Issue Invoice',self.issue,actions);button('New Invoice',self.reset_invoice,actions)
            self.add_item()
        def suggest_number(self,*args):
            if self.current is None:self.invoice_number.setText(self.store.next_number(self.fy.currentText()))
        def add_year(self):
            y,ok=QInputDialog.getText(self,'Financial year','Enter YYYY-YYYY, e.g. 2027-2028')
            if not ok:return
            if not re.fullmatch(r'\d{4}-\d{4}',y) or int(y[5:])!=int(y[:4])+1:alert(self,'Enter consecutive years.');return
            with self.store.db:self.store.db.execute('INSERT OR IGNORE INTO years(fy) VALUES(?)',(y,))
            for c in [self.fy,self.regfy]:
                if c.findText(y)<0:c.addItem(y)
            self.fy.setCurrentText(y)
        def add_item(self):
            n=self.items.rowCount();self.items.insertRow(n)
            for j,value in enumerate(['Professional fees','','0.00']):self.items.setItem(n,j,QTableWidgetItem(value))
        def remove_item(self):
            if self.items.currentRow()>=0:self.items.removeRow(self.items.currentRow());self.recalculate()
        def read_items(self):
            rows=[]
            for i in range(self.items.rowCount()):
                values=[self.items.item(i,j).text().strip() if self.items.item(i,j) else '' for j in range(3)]
                a=money(values[2]);
                if not a.is_finite() or a<0:raise ValueError('Amounts must be finite and nonnegative.')
                rows.append(dict(description=values[0],sac=values[1],amount=str(a)))
            return rows
        def recalculate(self,*args):
            try:
                t=totals(self.read_items(),self.pos.currentData(),self.rate.currentText());self.summary.setText('   |   '.join(f'{k.upper()}: INR {v}' for k,v in t.items()))
            except Exception:self.summary.setText('Enter valid service amounts to calculate GST.')
        def detect_state(self,text):
            text=text.strip().upper()
            if text[:2] in STATES:
                self.client_inputs['State Code'].setText(text[:2]);self.client_inputs['State'].setText(STATES[text[:2]]);self.pos.setCurrentIndex(self.pos.findData(text[:2]))
        def new_client(self):
            self.client_id=None;self.quick.setCurrentIndex(0)
            for x in self.client_inputs.values():x.clear()
        def fill_client(self,*args):
            i=self.quick.currentData();self.client_id=i
            if i:
                d=dict(self.store.clients())[i]
                for k,x in self.client_inputs.items():x.setText(d.get(k,''))
                code=d.get('State Code','')
                if code in STATES:self.pos.setCurrentIndex(self.pos.findData(code))
        def client_data(self):
            d={k:x.text().strip() for k,x in self.client_inputs.items()};d['GSTIN']=d['GSTIN'].upper();d['State Code']=d['State Code'].zfill(2)
            if not d['Legal Name'] or not d['Registered Address']:raise ValueError('Client legal name and registered address are required.')
            if d['State Code'] not in STATES:raise ValueError('Enter a valid Indian state code.')
            if d['GSTIN'] and not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]',d['GSTIN']):raise ValueError('GSTIN format is invalid. Leave blank for unregistered clients.')
            if d['GSTIN'] and d['GSTIN'][:2]!=d['State Code']:raise ValueError('GSTIN and client state code differ.')
            return d
        def save_client(self):
            try:
                self.client_id=self.store.save_client(self.client_data(),self.client_id);self.refresh_clients();alert(self,'Client saved locally.')
            except Exception as e:alert(self,e)
        def refresh_clients(self):
            selected=self.client_id;self.quick.blockSignals(True);self.quick.clear();self.quick.addItem('Select saved client / New client',None)
            clients=self.store.clients()
            for i,d in clients:self.quick.addItem(d['Legal Name']+'  |  '+d.get('GSTIN',''),i)
            self.quick.setCurrentIndex(max(0,self.quick.findData(selected)));self.quick.blockSignals(False)
            self.directory.setRowCount(0)
            for i,d in clients:
                if self.search.text().lower() not in ' '.join(d.values()).lower():continue
                r=self.directory.rowCount();self.directory.insertRow(r)
                for j,v in enumerate([str(i)]+[d.get(k,'') for k in FIELDS]):self.directory.setItem(r,j,QTableWidgetItem(v))
        def payload(self,draft=False):
            c=self.client_data();items=self.read_items();s=self.store.settings();dt=self.dt.date().toPyDate()
            if fy_for(dt)!=self.fy.currentText():raise ValueError('Invoice date must fall in selected April–March financial year.')
            if not items or any(not x['description'] or money(x['amount'])<=0 for x in items):raise ValueError('Add service descriptions and positive amounts.')
            if s['GST registered']=='Yes':
                if not re.fullmatch(r'27[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]',s['GSTIN'].upper()):raise ValueError('Save your Maharashtra supplier GSTIN in Settings before issuing a tax invoice.')
                if any(not re.fullmatch(r'\d{6}',x['sac']) for x in items):raise ValueError('Enter a six-digit SAC for every taxable service.')
            elif self.rate.currentText()!='0':raise ValueError('Unregistered supplier cannot charge GST. Select 0% GST.')
            return dict(fy=self.fy.currentText(),date=dt.isoformat(),number=self.store.validate_number(self.invoice_number.text()),client=c,firm=s,items=items,pos=self.pos.currentData(),rate=self.rate.currentText(),totals=totals(items,self.pos.currentData(),self.rate.currentText()))
        def preview(self,d):
            from PyQt6.QtPdf import QPdfDocument
            from PyQt6.QtPdfWidgets import QPdfView
            with tempfile.TemporaryDirectory(prefix='invoice_preview_') as td:
                path=Path(td)/'preview.pdf';export_professional_pdf(d,path)
                dialog=QDialog(self);dialog.setWindowTitle('Print-ready Invoice Preview');dialog.resize(940,860);layout=QVBoxLayout(dialog)
                document=QPdfDocument(dialog);document.load(str(path));view=QPdfView(dialog);view.setDocument(document);view.setPageMode(QPdfView.PageMode.MultiPage);view.setZoomMode(QPdfView.ZoomMode.FitToWidth);layout.addWidget(view);dialog.exec();document.close()
        def preview_draft(self):
            try:self.preview(self.payload(True))
            except Exception as e:alert(self,e)
        def issue(self):
            try:
                if self.current:raise ValueError('This invoice is already issued. Choose New Invoice for another.')
                d=self.payload();self.client_id=self.store.save_client(d['client'],self.client_id);self.current=self.store.issue(d);self.invoice_number.setText(self.current['number']);self.invoice_number.setReadOnly(True);self.refresh();alert(self,'Saved '+self.current['number']+'. Export from Invoice Register.')
            except Exception as e:alert(self,e)
        def reset_invoice(self):self.current=None;self.invoice_number.setReadOnly(False);self.suggest_number();self.items.setRowCount(0);self.add_item();self.dt.setDate(QDate.currentDate())
        def directory_tab(self):
            l=self.page('Client Directory');self.search=QLineEdit();self.search.setPlaceholderText('Search clients by any field');l.addWidget(self.search);self.search.textChanged.connect(self.refresh_clients)
            self.directory=QTableWidget(0,len(FIELDS)+1);self.directory.setAlternatingRowColors(True);self.directory.setHorizontalHeaderLabels(['ID']+FIELDS);self.directory.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.directory.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);l.addWidget(self.directory)
            b=QHBoxLayout();l.addLayout(b);button('Add New',lambda:(self.new_client(),self.tabs.setCurrentIndex(0)),b);button('Edit Selected',self.edit_client,b);button('Export Clients Backup',self.backup_clients,b);button('Restore Clients Backup',self.restore_clients,b)
        def edit_client(self):
            row=self.directory.currentRow()
            if row<0:return
            i=int(self.directory.item(row,0).text());self.quick.setCurrentIndex(self.quick.findData(i));self.fill_client();self.tabs.setCurrentIndex(0)
        def backup_clients(self):
            path,_=QFileDialog.getSaveFileName(self,'Export clients','','JSON (*.json)')
            if path:Path(path).write_text(json.dumps({'schema':1,'clients':[d for i,d in self.store.clients()]},indent=2),encoding='utf-8');alert(self,'Client backup saved.')
        def restore_clients(self):
            path,_=QFileDialog.getOpenFileName(self,'Restore clients','','JSON (*.json)')
            if not path:return
            try:
                data=json.loads(Path(path).read_text(encoding='utf-8'));rows=data['clients']
                if data.get('schema')!=1 or not isinstance(rows,list):raise ValueError('Unsupported backup.')
                if any(not isinstance(d,dict) or any(not isinstance(d.get(k,''),str) for k in FIELDS) or not d.get('Legal Name') for d in rows):raise ValueError('Invalid client data.')
                existing={json.dumps(d,sort_keys=True) for i,d in self.store.clients()}
                with self.store.db:
                    for d in rows:
                        d={k:d.get(k,'') for k in FIELDS};key=json.dumps(d,sort_keys=True)
                        if key not in existing:self.store.db.execute('INSERT INTO clients(data) VALUES(?)',(json.dumps(d),));existing.add(key)
                self.refresh_clients();alert(self,'Clients restored; existing clients retained. Exact duplicates skipped.')
            except Exception as e:alert(self,e)
        def register_tab(self):
            l=self.page('Invoice Register & Dashboard')
            filters=QHBoxLayout();l.addLayout(filters);filters.addWidget(QLabel('Financial year'));self.regfy=self.year_combo();filters.addWidget(self.regfy)
            filters.addWidget(QLabel('Client'));self.report_client=QComboBox();self.report_client.setMinimumWidth(280);filters.addWidget(self.report_client)
            self.status_filter=QComboBox();self.status_filter.addItems(['All statuses','Unpaid','Paid']);filters.addWidget(self.status_filter)
            self.regfy.currentTextChanged.connect(self.refresh_register);self.report_client.currentIndexChanged.connect(self.refresh_register);self.status_filter.currentIndexChanged.connect(self.refresh_register)
            self.kpi=QLabel();self.kpi.setStyleSheet('background:#eaf2fc;padding:18px;border-radius:8px;color:#163e70;font-size:12pt;font-weight:600;');self.kpi.setWordWrap(True);l.addWidget(self.kpi)
            note=QLabel('Choose a client to see their financial-year totals. Net fees exclude GST; receipts and outstanding include GST.\nTotals relate to invoices issued in the selected FY, even if payment arrived in another FY. Paid means full settlement; partial payments/TDS adjustments are not tracked.');note.setWordWrap(True);l.addWidget(note)
            self.chart=Chart();l.addWidget(self.chart)
            self.register=QTableWidget(0,8);self.register.setAlternatingRowColors(True);self.register.setMinimumHeight(240);self.register.setHorizontalHeaderLabels(['ID','Invoice No','Date','Client','Net INR','Total INR','Payment Status','Payment Date']);self.register.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch);self.register.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.register.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);l.addWidget(self.register)
            b=QHBoxLayout();l.addLayout(b);button('Mark as Paid',lambda:self.mark_payment(True),b);button('Mark as Unpaid',lambda:self.mark_payment(False),b);button('Export Filtered Register',self.export_register,b)
            b=QHBoxLayout();l.addLayout(b);button('Preview',lambda:self.selected_action('preview'),b);button('Export PDF',lambda:self.selected_action('pdf'),b);button('Export Excel',lambda:self.selected_action('excel'),b);button('Delete Invoice',self.delete_invoice,b);button('Full Database Backup',self.database_backup,b)
        def refresh_register(self,*args):
            key=self.report_client.currentData();clients={}
            for raw, in self.store.db.execute('SELECT data FROM invoices WHERE deleted=0 AND fy=?',(self.regfy.currentText(),)):
                c=json.loads(raw)['client'];clients[self.store.client_key(c)]=c
            self.report_client.blockSignals(True);self.report_client.clear();self.report_client.addItem('All clients',None)
            for k,c in sorted(clients.items(),key=lambda x:x[1]['Legal Name'].casefold()):
                self.report_client.addItem(c['Legal Name']+' | '+(c.get('GSTIN') or c.get('City','')+' | '+c.get('Registered Address','')[:30]),k)
            self.report_client.setCurrentIndex(max(0,self.report_client.findData(key)));self.report_client.blockSignals(False)
            report=self.store.report(self.regfy.currentText(),self.report_client.currentData());self.active_report=report
            self.register.setRowCount(0);values=[Decimal(0)]*12
            for i,d,paid,payment_date in report['rows']:
                values[(int(d['date'][5:7])-4)%12]+=Decimal(d['totals']['total'])
                if self.status_filter.currentText()=='Paid' and not paid:continue
                if self.status_filter.currentText()=='Unpaid' and paid:continue
                r=self.register.rowCount();self.register.insertRow(r)
                for j,v in enumerate([i,d['number'],d['date'],d['client']['Legal Name'],d['totals']['net'],d['totals']['total'],'Paid' if paid else 'Unpaid',payment_date or '']):
                    item=QTableWidgetItem(str(v));self.register.setItem(r,j,item)
                    if j==6:item.setForeground(QColor('#175ea8' if paid else '#c66c16'))
            self.chart.values=values;self.chart.update()
            self.kpi.setText(f"Invoices: {len(report['rows'])}  |  Net fees invoiced: INR {report['net']:,.2f}  |  Total incl. GST: INR {report['gross']:,.2f}\nReceived incl. GST: INR {report['received']:,.2f}  |  Outstanding incl. GST: INR {report['outstanding']:,.2f}  |  Settled net fees: INR {report['paid_net']:,.2f}")
        def mark_payment(self,paid):
            try:
                i,d=self.selected();payment_date=None
                if paid:
                    payment_date,ok=QInputDialog.getText(self,'Mark invoice as paid','Full settlement date (YYYY-MM-DD)',text=date.today().isoformat())
                    if not ok:return
                    payment_date=payment_date.strip()
                elif QMessageBox.question(self,'Mark as unpaid',f"Reopen {d['number']} as unpaid?")!=QMessageBox.StandardButton.Yes:return
                self.store.set_paid(i,paid,payment_date);self.refresh_register()
            except Exception as e:alert(self,e)
        def export_register(self):
            path,_=QFileDialog.getSaveFileName(self,'Export filtered register','Invoice_Register.xlsx','Excel (*.xlsx)')
            if not path:return
            try:
                if not path.lower().endswith('.xlsx'):path+='.xlsx'
                wb=Workbook();ws=wb.active;ws.title='Invoice Register'
                ws.append(['Financial year',self.regfy.currentText()]);ws.append(['Client',self.report_client.currentText()]);ws.append(['Status filter',self.status_filter.currentText()]);ws.append(['Invoice No','Date','Client','Net INR','Total INR','Payment Status','Payment Date'])
                for r in range(self.register.rowCount()):
                    vals=[self.register.item(r,c).text() for c in range(1,8)];vals[3]=float(vals[3]);vals[4]=float(vals[4]);ws.append(vals)
                for col,width in [('A',22),('B',20),('C',50),('D',20),('E',20),('F',20),('G',20)]:ws.column_dimensions[col].width=width
                for row in ws.iter_rows(min_row=5):
                    for cell in row[3:5]:cell.number_format='#,##0.00'
                ws.freeze_panes='A5';ws.auto_filter.ref=f'A4:G{ws.max_row}';wb.save(path);alert(self,'Filtered register exported.')
            except Exception as e:alert(self,e)
        def selected(self):
            row=self.register.currentRow()
            if row<0:raise ValueError('Select an invoice in the register.')
            i=int(self.register.item(row,0).text());return i,json.loads(self.store.db.execute('SELECT data FROM invoices WHERE id=?',(i,)).fetchone()[0])
        def selected_action(self,action):
            try:
                i,d=self.selected()
                if action=='preview':self.preview(d);return
                ext='pdf' if action=='pdf' else 'xlsx';path,_=QFileDialog.getSaveFileName(self,'Export invoice',d['number'].replace('/','_')+'.'+ext,f'{ext.upper()} (*.{ext})')
                if not path:return
                if not path.lower().endswith('.'+ext):path+='.'+ext
                if action=='pdf':
                    export_professional_pdf(d,path)
                else:self.excel(d,path)
                alert(self,'Invoice exported.')
            except Exception as e:alert(self,e)
        def excel(self,d,path):
            wb=Workbook();ws=wb.active;ws.title='Invoice';s=d['firm'];c=d['client'];t=d['totals']
            rows=[[s['Firm']],[s['Address']],[s['Email']+' | '+s['Phone']],['Supplier GSTIN',s['GSTIN']],['TAX INVOICE' if s['GST registered']=='Yes' else 'INVOICE'],['Invoice No',d['number']],['Date',d['date']],['Financial Year',d['fy']]]
            rows += [[k,c.get(k,'')] for k in FIELDS]
            rows += [['Place of supply',d['pos']+' - '+STATES[d['pos']]],['Reverse charge','No'],[],['No.','Description','SAC','Net INR']]
            for r in rows:ws.append(r)
            header=ws.max_row
            for i,x in enumerate(d['items'],1):ws.append([i,x['description'],x['sac'],float(x['amount'])]);ws.cell(ws.max_row,4).number_format='#,##0.00'
            ws.append([])
            for key,label in [('net','Net fees'),('cgst','CGST'),('sgst','SGST'),('igst','IGST'),('total','Total INR')]:ws.append(['',label,'',float(t[key])]);ws.cell(ws.max_row,4).number_format='#,##0.00'
            ws.append(['GST rate %',float(d['rate'])]);ws.append(['Amount in words',words(t['total'])])
            for k in ['Bank','Branch','Beneficiary','Account','IFSC','Terms']:ws.append([k,s[k]])
            ws.append(['For '+s['Firm']]);ws.append(['Authorised Signatory'])
            for col,width in [('A',23),('B',66),('C',20),('D',24)]:ws.column_dimensions[col].width=width
            for row in ws:
                for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True);cell.font=Font(name='Calibri',size=11)
                ws.row_dimensions[row[0].row].height=34
            for r in [1,2,3,5]:
                ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=3)
            ws.row_dimensions[1].height=42;ws.row_dimensions[2].height=38;ws.row_dimensions[3].height=30
            ws.row_dimensions[5].height=32
            for r in range(header+1,header+1+len(d['items'])):
                text=str(ws.cell(r,2).value or '');ws.row_dimensions[r].height=max(36,16*((len(text)//55)+text.count('\n')+1))
            for r in [1,5,header]:
                for cell in ws[r]:cell.fill=PatternFill('solid',fgColor='173E70');cell.font=Font(color='FFFFFF',bold=True,size=12)
            # Images in Excel are optional: openpyxl uses Pillow only if images are present.
            for key,anchor in [('Logo','D1'),('Signature / stamp',f'C{ws.max_row-1}')]:
                if s[key] and Path(s[key]).exists():
                    if importlib.util.find_spec('PIL') is None:subprocess.check_call([sys.executable,'-m','pip','install','Pillow'])
                    img=XLImage(s[key]);ratio=min(135/img.width,65/img.height);img.width*=ratio;img.height*=ratio;ws.add_image(img,anchor)
            ws.sheet_properties.pageSetUpPr.fitToPage=True;ws.page_setup.orientation='portrait';ws.page_setup.paperSize=ws.PAPERSIZE_A4;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0;ws.print_options.horizontalCentered=True;ws.print_title_rows=f'{header}:{header}';wb.save(path)
        def delete_invoice(self):
            try:
                i,d=self.selected()
                if QMessageBox.question(self,'Delete invoice',f"Remove {d['number']} from active invoices? Its number remains reserved and its record is retained for audit.")!=QMessageBox.StandardButton.Yes:return
                with self.store.db:self.store.db.execute('UPDATE invoices SET deleted=1 WHERE id=?',(i,))
                self.refresh_register()
            except Exception as e:alert(self,e)
        def database_backup(self):
            path,_=QFileDialog.getSaveFileName(self,'Backup database','','SQLite (*.sqlite3)')
            if path:
                try:
                    if Path(path).resolve()==(ROOT/'invoices.sqlite3').resolve():raise ValueError('Choose a different backup location.')
                    with sqlite3.connect(path) as dest:self.store.db.backup(dest)
                    alert(self,'Database backup saved. Also copy the assets folder to preserve images.')
                except Exception as e:alert(self,e)
        def settings_tab(self):
            l=self.page('Firm & Bank Settings');scroll=QScrollArea();scroll.setWidgetResizable(True);w=QWidget();f=QFormLayout(w);scroll.setWidget(w);l.addWidget(scroll);self.settings_inputs={}
            for k,v in self.store.settings().items():
                if k=='GST registered':x=QComboBox();x.addItems(['Yes','No']);x.setCurrentText(v)
                else:x=QLineEdit(v)
                self.settings_inputs[k]=x;f.addRow('IFSC Code' if k=='IFSC' else k,x)
                if k=='IFSC':x.setPlaceholderText('Enter bank IFSC code, e.g. KARB0000123');x.setMaxLength(11)
                if k in ['Logo','Signature / stamp']:
                    b=QPushButton('Upload '+k);b.clicked.connect(lambda checked=False,key=k:self.upload_asset(key));f.addRow('',b)
            note=QLabel('Enter actual GSTIN and unmasked bank details before use. GSTIN prefix sets client state; confirm place of supply for exceptions.\n18% is a configurable default, not a classification opinion. Image signature is not a digital signature.\nDomestic forward-charge invoices only. IRN/e-invoicing, exports/SEZ and reverse-charge workflows are not implemented.\nLogo reference: https://www.icai.org/post/icai-unveils-new-ca-india-logo');note.setWordWrap(True);l.addWidget(note)
            button('Save Settings',self.save_settings,l)
            button('Change Security PIN',self.change_pin,l)
        def upload_asset(self,key):
            path,_=QFileDialog.getOpenFileName(self,'Select image','','Images (*.png *.jpg *.jpeg *.bmp)')
            if path:
                from PyQt6.QtGui import QImage
                if QImage(path).isNull():alert(self,'Invalid image.');return
                (ROOT/'assets').mkdir(exist_ok=True);target=ROOT/'assets'/('logo' if key=='Logo' else 'signature')
                target=target.with_suffix(Path(path).suffix.lower())
                if Path(path).resolve()!=target.resolve():shutil.copy2(path,target)
                self.settings_inputs[key].setText(str(target))
        def save_settings(self):
            d={k:(x.currentText() if isinstance(x,QComboBox) else x.text().strip()) for k,x in self.settings_inputs.items()};d['GSTIN']=d['GSTIN'].upper()
            d['IFSC']=d['IFSC'].upper()
            if d['IFSC'] and not re.fullmatch(r'[A-Z]{4}0[A-Z0-9]{6}',d['IFSC']):alert(self,'IFSC must contain 11 characters: four letters, 0, then six letters/digits.');return
            with self.store.db:
                for k,v in d.items():self.store.db.execute('INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)',(k,v))
            alert(self,'Settings saved. Existing invoices retain their original details.')
        def refresh(self):self.refresh_clients();self.refresh_register()
    app=QApplication.instance() or QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet('QWidget {font-family:Segoe UI;font-size:10pt;color:#243750;} QMainWindow,QDialog {background:#eef3fa;} QWidget#banner {background:white;border-radius:12px;border-bottom:4px solid #4a94db;} QLabel#brandTitle {font-size:22pt;font-weight:700;color:#175ea8;} QLabel#muted {color:#60748e;font-size:9pt;} QLabel#title {font-size:17pt;font-weight:700;color:#175ea8;} QLineEdit,QComboBox,QDateEdit {min-height:25px;padding:6px 9px;border:1px solid #c7d5e6;border-radius:6px;background:white;selection-background-color:#175ea8;} QLineEdit:focus,QComboBox:focus,QDateEdit:focus {border:2px solid #3884cc;} QPushButton {background:#175ea8;color:white;padding:10px 15px;border:0;border-radius:6px;font-weight:600;} QPushButton:hover {background:#2877bd;} QPushButton:pressed {background:#123c69;} QTabWidget::pane {background:white;border:1px solid #d1ddeb;border-radius:8px;} QTabBar::tab {padding:13px 20px;margin-right:5px;background:#e0eaf6;color:#365779;border-top-left-radius:7px;border-top-right-radius:7px;font-weight:600;} QTabBar::tab:selected {background:#175ea8;color:white;} QTableWidget {background:white;alternate-background-color:#f1f6fd;border:1px solid #d1ddeb;border-radius:6px;gridline-color:#e1e9f4;selection-background-color:#d4e6fa;selection-color:#173e70;} QHeaderView::section {background:#e4edf9;padding:10px;border:0;border-bottom:2px solid #4a94db;font-weight:600;} QScrollArea {border:0;background:white;} QStatusBar {background:#e0eaf7;color:#3c5878;} QTextBrowser {background:white;border:1px solid #d1ddeb;padding:16px;}')
    if PinDialog(setup=security.read() is None).exec()!=QDialog.DialogCode.Accepted:return
    window=App();window.show();app.exec()
if __name__=='__main__':
    try:run()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            import tkinter.messagebox
            tkinter.messagebox.showerror('Invoice creation Utility',f'{exc}\n\nManual install:\npython -m pip install PyQt6 openpyxl Pillow reportlab')
        except Exception:pass
