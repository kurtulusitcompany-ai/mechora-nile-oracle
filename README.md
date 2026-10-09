# Mechora (MCH) — TRON Nile Testnet referans fiyat oracle

Bu paket **Node.js ve JavaScript kullanmaz**. GitHub Actions üzerinde Python ile çalışır. CoinGecko'dan gerçek **TRX/USD fiyatı** ve **TRX market cap** verisini alır ve **TRON Nile Testnet üzerinde yayımlanmış MCH sözleşmesine yalnızca TRX referans alanları olarak** yazar. **MCH'nin gerçek fiyatını/market cap'ini oluşturmaz, TRX teminatı veya 1:1 dönüşüm sağlamaz.**

> Ön koşul: TronIDE'de daha önce yayımlanan Mechora kontratında `updateTRXMarket(uint256,uint256,uint256)` veya `updateTRXReference(uint256,uint256,uint256)` veya `updateTrxReference(uint256,uint256,uint256)` fonksiyonu bulunmalı. **Bu kod sözleşmeyi güncellemez ve yeni token basmaz.**

## 1. Test-only oracle wallet oluştur

TronLink içinde **sadece Nile testnet için yeni ayrı bir cüzdan** oluştur. Asıl MCH sahibi cüzdanını / gerçek varlıklarını kullandığın cüzdanı otomasyona bağlama. Nile musluğundan bu yeni adres için test TRX al: https://nileex.io/join/getJoinPage.

TronIDE'de, daha önce kontratı deploy eden **owner cüzdanıyla** MCH sözleşmesini aç. Son paylaştığımız MCH kodunda bulunan **`setOracle(address)`** fonksiyonuna, yeni ayrı Nile oracle cüzdanının `T...` adresini ver ve TronLink'ten imzalayarak yetkilendir. Böylece GitHub ile kullanacağın anahtar sadece referans verilerini yazabilir, token arzı ve owner ayrı kalır.

**Çok önemli:** Kontratında `setOracle` yoksa ve sadece `onlyOwner` ile `updateTRXReference` varsa owner özel anahtarını GitHub'a yükleme. Önce daha az yetkili oracle rolü olan sözleşme sürümüne geç.

## 2. GitHub üzerinde dosyaları yükle

1. https://github.com/new sayfasında `mechora-nile-oracle` adlı yeni bir repository oluştur. Ücretsiz public repository için standart GitHub Actions çalıştırmaları ücretsizdir; kod açık görünür, **özel anahtar yalnızca secret olmalıdır**. İstersen private repo kullan (plan kotası vardır).
2. ZIP içindeki `oracle.py`, `requirements.txt`, `tests/test_oracle.py` ve **`.github/workflows/nile-oracle.yml`** dosyalarını aynı dizin yapısıyla depoya yükle. GitHub web yüklemesinde gizli `.github` klasörünü de koru.
3. Repository **Settings → Secrets and variables → Actions → Variables** bölümünden şu 3 değişkeni gir:

| Variable | Değer |
|---|---|
| `MCH_CONTRACT_ADDRESS` | Nile'da deploy ettiğin MCH tokenin `T...` kontrat adresi |
| `UPDATE_FUNCTION` | En son paylaştığımız kontrat için `updateTRXMarket`, eski sürüm için `updateTRXReference` veya `updateTrxReference` |
| `ENABLE_NILE_WRITES` | Başlangıçta `false` (yalnızca okuma) |

4. **Secrets** bölümünden `NILE_ORACLE_PRIVATE_KEY` ekle. Yalnızca ayrı bir **Nile-only oracle test cüzdanının** 64 karakterli hex özel anahtarını ekle. Bu anahtarı **kodda, Issues'da, ChatGPT'de veya chat'te paylaşma**. Özel anahtarın girilmesi yalnızca GitHub'ın **Secrets** ekranında yapılmalı.
5. İsteğe bağlı: CoinGecko Demo API anahtarın varsa `COINGECKO_DEMO_API_KEY` adlı secret ekle. Bu yokken kamuya açık CoinGecko endpoint'i denenir; API 429/rate limit alınabilir.

## 3. Önce test et, ardından otomatiği aç

GitHub'da **Actions → Mechora Nile TRX reference oracle → Run workflow** seçeneğiyle çalıştır. Varsayılan ayar sadece CoinGecko verisini okur, işlem göndermez. Çalıştırma kaydında `READ-ONLY` görmelisin.

Daha sonra `ENABLE_NILE_WRITES` değişkenini `true` yap. GitHub Actions yaklaşık 30 dakikada bir çalışacak, en yeni TRX fiyatını ve piyasa değerini Nile sözleşmene yazacaktır; GitHub'ın planlayıcı işleri gecikebilir. **Her on-chain yazma Energy/Bandwidth tüketir ve kaynak yoksa test TRX yakabilir.** Oraclenin test TRX bakiyesini kontrol et.

## 4. Nereden göreceğim?

TronIDE → Deployed Contracts → Mechora bölümünde:

- `trxPriceUsdE8`: TRX'in dolar fiyatı × 100.000.000
- `trxMarketCapUsd`: **TRX'in** USD piyasa değeri (MCH market cap değil)
- `sourceUpdatedAt` / `trxSourceUpdatedAt`: son CoinGecko verisinin zamanı
- `mchReferencePriceUsdE8`: 1 MCH = 1 TRX varsayımına göre **teorik referans fiyat**
- `mchIndicativeFDVUsdE8`: MCH arzı × TRX referans fiyatı (teorik FDV, gerçek piyasa değeri değil)

Sözleşmenin güncel fonksiyonları, hangi sürümü deploy ettiğine göre farklı olabilir.

## Tek seferlik yerel test (opsiyonel)

Bilgisayarında Python 3.11+ varsa:

```bash
pip install -r requirements.txt
python oracle.py
python -m unittest discover -s tests -v
```

`ENABLE_NILE_WRITES` belirtilmedikçe **hiçbir işlem gönderilmez**.

## Güvenlik ve sınırlamalar

- Bu paket **sadece TRON Nile** ağını kullanır, mainnet'e otomatik bağlanmaz.
- `MCH_CONTRACT_ADDRESS` yalnızca Nile'da yayımlanmış gerçek token kontratına ait olmalı.
- Fiyat gerçek bir sabitleme değildir; fiyat teminatı / TRX'e dönüşüm fonksiyonu yoktur.
- Cüzdanlarda ve TRONSCAN'de MCH'nin USD değeri olarak görünmesini garanti etmez.
- GitHub Secrets bile üçüncü taraf altyapısına özel anahtar emanet eder; sadece **test cüzdanı** kullan.
- CoinGecko veya Nile erişilemezse veri güncellenmez; sistem eski fiyatı "canlı" diye sunmamalıdır. Sözleşmede kaynak zamanı saklanır.

Kaynaklar: https://tronpy.readthedocs.io/en/latest/contract.html ; https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax ; https://developers.tron.network/docs/getting-testnet-tokens-on-tron
