# Yerel Çalıştırma Rehberi

Bu dosya geliştirme sırasında doğrulanmış kurulum ve çalıştırma komutlarını tutar. Final README değildir; teslim aşamasında güncel bilgiler Türkçe README'ye aktarılacaktır.

## Ön koşullar

- Python 3.11 veya üzeri
- Poppler (`pdftoppm` komutu için)
- Tesseract OCR ile Türkçe ve İngilizce dil paketleri

macOS kurulumu:

```bash
brew install poppler
brew install tesseract tesseract-lang
```

Kurulumu doğrulama:

```bash
which pdftoppm
tesseract --list-langs
```

Dil listesinde en az `tur` ve `eng` bulunmalıdır.

Case kaynak raporu `data/source/report.pdf` yolunda teslim kapsamındadır. Doğrulanan SHA-256 değeri `25e4afe4c27bd2b3bb17a943a323e265520e68981c349f300d9248b3f3bfd7e0` şeklindedir.

## Python ortamı

Proje kökünde:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

Doğrulanan doğrudan ve geçişli Python bağımlılıkları `requirements.txt` içinde sabitlenmiştir; son satır projeyi normal yerel wheel olarak kurar. Paket metadatası, doğrudan çalışma bağımlılıkları ve sabit `setuptools==80.9.0` build backend sürümü ayrıca `pyproject.toml` içinde tutulur. Normal wheel kurulumu, editable `.pth` dosyalarının macOS/iCloud `hidden` bayrağından etkilenmesini önler. Poppler ve Tesseract sistem bağımlılıkları Python requirements dosyasından kurulmaz.

## Testler

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## PSM karşılaştırması

PSM 3, 4, 6 ve 11 sonuçlarını aynı sayfalar üzerinde karşılaştırmak için:

```bash
python3 scripts/psm_comparison.py \
  --config configs/default.json \
  --expectations evaluation/psm_expectations.json \
  --psm 3 4 6 11
```

Görselleri yeniden üretmek gerekirse `--rerender` eklenir. Sonuçlar `work/evaluation/` altında oluşur.

## Aşama 1 — Özet tabloların OCR çıktısı

```bash
PYTHONPATH=src python3 -m ykt_case.cli \
  --config configs/default.json \
  --stage summary-ocr
```

Başlıca çıktılar:

- `work/rendered/summary/`: yapılandırmada seçilen özet sayfaların görüntüleri
- `work/ocr/summary_ocr.json`: kelime, güven skoru ve koordinat içeren OCR çıktısı

## Aşama 2 — Özet tabloların yapılandırılması

```bash
PYTHONPATH=src python3 -m ykt_case.cli \
  --config configs/default.json \
  --stage summary-structure
```

Başlıca çıktı:

- `work/structured/summary_tables.json`: dönemler, dipnot referansları, finansal değerler, satır metrikleri ve uyarılar

## Aşama 3 — Hedef dipnotun doküman genelinde bulunması

```bash
PYTHONPATH=src python3 -m ykt_case.cli \
  --config configs/default.json \
  --stage note-locate
```

Bu aşama sayfa numarası enjekte etmeden tüm dokümanı düşük çözünürlükte tarar. Tam doküman OCR'ı makineye göre birkaç dakika sürebilir.

Başlıca çıktılar:

- `work/rendered/note_scan/`: arama amacıyla üretilen düşük çözünürlüklü sayfalar
- `work/notes/note_locations.json`: hedef dipnotun bulunan sayfaları, kanıtları, güven skoru ve uyarıları

## Aşama 4 — Bulunan dipnot tablolarının yapılandırılması

```bash
PYTHONPATH=src python3 -m ykt_case.cli \
  --config configs/default.json \
  --stage note-extract
```

Bu aşama `note-locate` çıktısındaki sayfaları 300 DPI'da yeniden üretir; bilinen sayfa veya değerleri çalışma koduna gömmeden tekrarlanan sayısal sütun geometrisinden tabloları ve satırları çıkarır.

Başlıca çıktılar:

- `work/ocr/note_ocr.json`: bulunan dipnot sayfalarının yüksek çözünürlüklü, koordinatlı OCR çıktısı
- `work/structured/note_tables.json`: sütun başlıkları, satır etiketleri, normalize değerler, kaynak koordinatları, güven skorları ve uyarılar

## Aşama 5A — Açıklanabilir baseline ilişki eşleştirmesi

```bash
PYTHONPATH=src python3 -m ykt_case.cli \
  --config configs/default.json \
  --stage match-baseline
```

Bu aşama yalnızca yapılandırılmış özet satırları ile aynı dipnota ait yapılandırılmış dipnot satırlarını kullanır. Lexical benzerlik, tam sayısal dönem kapsamı, satır türü uyumu ve extraction güvenini ayrı kanıtlar olarak raporlar; top-k adayları saklar ve gerektiğinde birden fazla dipnot satırı seçebilir veya eşleşmeden kaçınabilir.

Başlıca çıktı:

- `work/matching/baseline_relations.json`: aday skorları, özellikler, seçilen sıfır/bir/çok satır, kapsam, belirsizlik ve ilişki güveni

Baseline çıktısını çalışma zamanından ayrı tutulan insan değerlendirme etiketleriyle ölçmek için:

```bash
PYTHONPATH=src python3 scripts/evaluate_relations.py \
  --predictions work/matching/baseline_relations.json \
  --expectations evaluation/relation_expectations.json \
  --output work/evaluation/baseline_relation_evaluation.json
```

Bu küçük kontrol kümesinden üretilen metrikler yalnızca keşifsel olarak yorumlanır; genel model performansı iddiası değildir.

## Aşama 5B — Multilingual embedding ilişki eşleştirmesi

`requirements.txt` semantic bağımlılıkları da içerir. Yerel embedding aşaması şu komutla çalıştırılır:

```bash
PYTHONPATH=src python3 -m ykt_case.cli \
  --config configs/default.json \
  --stage match-semantic
```

İlk çalıştırmada yapılandırılmış model yerel cache'e indirilebilir; sonraki çalışmalarda `semantic.allow_download` false yapılarak yalnızca cache kullanımı zorlanabilir. Model veya bağımlılık kullanılamazsa çıktı bunu `fallback_used: true` ile bildirir ve baseline sonucunu açıkça fallback olarak üretir.

Başlıca çıktı:

- `work/matching/semantic_relations.json`: semantic, sayısal, yapısal ve extraction kanıtlarıyla sıralanmış ilişkiler ve model çalışma bilgileri

Aynı evaluator ile ölçmek için:

```bash
PYTHONPATH=src python3 scripts/evaluate_relations.py \
  --predictions work/matching/semantic_relations.json \
  --expectations evaluation/relation_expectations.json \
  --output work/evaluation/semantic_relation_evaluation.json
```

İki yöntemin metrik ve örnek bazlı sıralama farklarını tek raporda görmek için:

```bash
PYTHONPATH=src python3 scripts/compare_relation_methods.py \
  --baseline work/matching/baseline_relations.json \
  --semantic work/matching/semantic_relations.json \
  --expectations evaluation/relation_expectations.json \
  --output work/evaluation/relation_method_comparison.json
```

## Aşama 6 — Güven birleştirme ve validasyon

```bash
PYTHONPATH=src python3 -m ykt_case.cli \
  --config configs/default.json \
  --stage validate
```

Bu aşama önceki artefaktları değiştirmez. Yapısal, biçimsel ve finansal kontrolleri çalıştırır; her kalite kapısı için ölçüm, eşik, karşılaştırma yönü, aksiyon ve gerekçeyi kaydeder. İlişki güvenini matcher skoru, tam dönem kapsamı, extraction kalitesi, iki yöntem arasındaki anlaşma ve belirsizlik/fallback cezalarıyla yeniden birleştirir. Son güven değeri kalibre edilmiş olasılık olarak yorumlanmaz.

Başlıca çıktı:

- `work/validation/validation_report.json`: kalite kapıları, kontrol kanıtları, finansal mutabakatlar, durdurma/uyarı sonuçları ve nihai ilişki güvenleri

## Embedding model karşılaştırması

Üç yerel çok dilli modeli aynı 38 aday ve evaluator üzerinde karşılaştırmak için:

```bash
PYTHONPATH=src python3 scripts/benchmark_embedding_models.py \
  --config configs/default.json \
  --expectations evaluation/relation_expectations.json \
  --output work/evaluation/embedding_model_benchmark.json \
  --warm-runs 3 \
  --allow-download
```

`--allow-download` yalnızca herkese açık model ağırlıklarını yerel cache'e indirir; doküman, OCR veya finansal veri dış servise gönderilmez. Modeller cache'deyse bayrak kaldırılarak offline çalışma zorlanabilir. Çıktı; sabit karşılaştırma koşullarını, exact revision/lisans/boyut bilgisini, warm süreleri, keşifsel metrikleri ve örnek bazlı Top-5 sıralamalarını içerir.

## Aşama 7 — Tek komutluk uçtan uca çalışma

Semantic bağımlılığı ve model cache'i hazırlandıktan sonra zorunlu yedi runtime aşaması tek komutla yeniden üretilebilir:

```bash
PYTHONPATH=src python3 -m ykt_case.cli \
  --config configs/default.json \
  --stage all
```

Komut varsayılan olarak yedi ana aşama için ilerleme çubuğu gösterir. Sayfa bazlı OCR işlemleri ayrıca gerçek sayfa sayısı, işleme hızı ve tahmini kalan süreyi raporlar. Embedding modelinin yükleme toplamı ölçülemediği için bu bölümde sahte yüzde yerine durum mesajı gösterilir.

CI, yönlendirilmiş terminal çıktısı veya sessiz çalışma için ilerleme kapatılabilir:

```bash
PYTHONPATH=src python3 -m ykt_case.cli \
  --config configs/default.json \
  --stage all \
  --no-progress
```

Bu komut insan-kontrollü `evaluation/` etiketlerini okumaz. Özet OCR, özet yapılandırma, doküman-geneli dipnot bulma, dipnot tablo çıkarımı, baseline eşleştirme, semantic eşleştirme ve validasyonu sırasıyla çalıştırır.

Başlıca çıktılar:

- `outputs/result.json`: version `1.0` final extraction, otomatik ilişkiler, güven kanıtı, validasyon ve uyarılar
- `outputs/run_manifest.json`: kaynak/config checksum'ları, ortam ve model bağımlılıkları, seed, Git durumu, aşama süreleri/statüleri, ara çıktı checksum'ları, fallback olayları ve final çıktı checksum'ı
- `outputs/run_events.jsonl`: aşama başlangıç/bitiş ve run sonucu olayları

Sürüm geçmişi ve ayrıntılı geliştirme tanılama kopyaları ayrıca `work/manifests/` ve `work/logs/` altında tutulur. Teslim JSON'u yalnızca sabit `outputs/run_manifest.json` yoluna referans verir.

Son değerlendirme raporlarını sabit teslim yollarına kopyalayıp kapsam-kanıt indeksini üretmek için:

```bash
PYTHONPATH=src python3 scripts/prepare_delivery_artifacts.py
```

Bu komut `outputs/evaluation/` raporlarını ve her kapsam maddesini dosya/JSON alanıyla eşleyen `outputs/delivery_index.json` dosyasını üretir. İndeks ayrıca teslim edilen runtime/değerlendirme artefaktlarının boyut ve SHA-256 değerlerini kaydeder. Eksik bir artefakt varsa sessizce kopyalamak yerine açık hata verir.

2026-10-15 tarihinde `.venv/`, `work/` ve `outputs/` silindikten sonra yalnızca `requirements.txt` ile kurulan temiz ortamda gerçek çalışma yeniden doğrulandı. Sonuç `completed_with_warnings`; yedi aşamanın tamamı bitti, stop-gate hatası ve fallback oluşmadı. Çıktı veya manifest içindeki `failed` durumu başarılı çalışma olarak yorumlanmamalıdır; CLI bu durumda sıfırdan farklı çıkış kodu verir.

Son manifest ayrıca çözülmüş embedding model revision'ını, CPU cihazını, 15 kalite kapısının tam sonucunu ve validasyon özetini doğrudan taşır. Semantic fallback tetiklenirse olay kaydı başarısız semantic sonucu, kullanılan baseline sonucu ve semantic kanıt kaybını ayrı alanlarda gösterir.

## Sorun giderme

`pdftoppm is required but was not found on PATH` hatası Poppler'ın kurulu veya terminal PATH'inde erişilebilir olmadığını gösterir. `brew install poppler` sonrasında `which pdftoppm` ile kontrol edilir.

OCR dili bulunamıyorsa `tesseract --list-langs` çıktısı kontrol edilir; `tur` yoksa `tesseract-lang` kurulmalıdır.
