import unicodedata

cadena =" Vendo Dólares a 60 cup"
cadena_normalize=unicodedata.normalize('NFKD', cadena).encode('ASCII', 'ignore').lower()
print(str(cadena_normalize).find("dolares"))