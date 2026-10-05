import pandas as pd
import joblib
import warnings
from pathlib import Path
warnings.filterwarnings("ignore")

from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, classification_report,
                             confusion_matrix)
from sklearn.preprocessing import OrdinalEncoder
from sklearn.impute import SimpleImputer
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'dataset'
ARTIFACT_DIR = BASE_DIR / 'artifacts'
ARTIFACT_DIR.mkdir(exist_ok=True)

fe = pd.read_csv(DATA_DIR / 'floodevents_indofloods.csv')
pr = pd.read_csv(DATA_DIR / 'precipitation_variables_indofloods.csv')
cc = pd.read_csv(DATA_DIR / 'catchment_characteristics_indofloods.csv')

fe['GaugeID'] = fe['EventID'].str.rsplit('-', n=1).str[0]
df = fe.merge(pr, on='EventID').merge(cc, on='GaugeID')
print(f"Full merged dataset: {df.shape[0]} events × {df.shape[1]} columns")
print(f"Label: {df['Flood Type'].value_counts().to_dict()}\n")

df['start_month']       = pd.to_datetime(df['Start Date']).dt.month
df['is_monsoon']        = df['start_month'].between(6, 9).astype(int)
df['rainfall_1d']       = df['T1d']
df['rainfall_3d']       = df['T3d']
df['rainfall_5d']       = df['T5d']
df['rainfall_10d']      = df['T10d']
df['intensity_d1']      = df['T1d']
df['intensity_d2_3']    = df['T3d']  - df['T1d']
df['intensity_d4_7']    = df['T7d']  - df['T3d']
df['intensity_d8_10']   = df['T10d'] - df['T7d']
df['rise_rate']         = df['Peak Flood Level (m)'] / df['Time to Peak (days)'].replace(0, 1)
df['rain_per_day']      = df['rainfall_10d'] / df['Event Duration (days)'].replace(0, 1)

EVENT_FEATURES = [
    'rainfall_1d', 'rainfall_3d', 'rainfall_5d', 'rainfall_10d',
    'intensity_d1', 'intensity_d2_3', 'intensity_d4_7', 'intensity_d8_10',
    'Peak Discharge Q (cumec)', 'Flood Volume (cumec)',
    'Event Duration (days)', 'Time to Peak (days)', 'Recession Time (day)',
    'Peak Flood Level (m)', 'Num Peak FL',
    'rise_rate', 'rain_per_day',
    'start_month', 'is_monsoon',
]

CATCHMENT_NUM = [
    'Drainage Area', 'Catchment Relief', 'Drainage Density',
    'Ruggedness Number', 'Stream Order', 'Form Factor',
    'Sinuosity Index', 'Elongation Ratio', 'Infiltration Number',
    'Annual Mean Temperature', 'Annual Precipitation',
    'Precipitation of Wettest Month', 'Precipitation Seasonality',
    'Population Density', 'Urban percentage', 'Road Density',
    '2015_HDI', 'Night Light',
]

CATCHMENT_CAT = ['Land cover', 'Soil type', 'KoppenGeiger Climate Type', 'lithology type']

ALL_NUM = EVENT_FEATURES + CATCHMENT_NUM
ALL_FEATURES = ALL_NUM + CATCHMENT_CAT

print(f"Total features: {len(ALL_FEATURES)}  "
      f"({len(ALL_NUM)} numeric + {len(CATCHMENT_CAT)} categorical)\n")

X = df[ALL_FEATURES].copy()
y = (df['Flood Type'] == 'Severe Flood').astype(int)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
scale_pos = (y_train == 0).sum() / (y_train == 1).sum()

encoder = OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
imputer = SimpleImputer(strategy='median')

X_train = X_train.copy()
X_test = X_test.copy()
X_train[CATCHMENT_CAT] = encoder.fit_transform(X_train[CATCHMENT_CAT])
X_test[CATCHMENT_CAT] = encoder.transform(X_test[CATCHMENT_CAT])
X_train_imp = pd.DataFrame(imputer.fit_transform(X_train), columns=ALL_FEATURES, index=X_train.index)
X_test_imp = pd.DataFrame(imputer.transform(X_test), columns=ALL_FEATURES, index=X_test.index)
print(f"NaNs after imputation: {X_train_imp.isnull().sum().sum() + X_test_imp.isnull().sum().sum()}")

model = XGBClassifier(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.04,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=3,
    scale_pos_weight=scale_pos,
    eval_metric='logloss',
    early_stopping_rounds=25,
    random_state=42,
    verbosity=0,
)

# Early stopping uses a validation slice carved from the TRAINING data so the
# held-out test set is never used for model selection (no leakage).
X_fit, X_val, y_fit, y_val = train_test_split(
    X_train_imp, y_train, test_size=0.15, random_state=42, stratify=y_train
)
model.fit(X_fit, y_fit, eval_set=[(X_val, y_val)], verbose=False)
print(f"Best iteration (early stopping): {model.best_iteration}")

y_pred = model.predict(X_test_imp)
y_prob = model.predict_proba(X_test_imp)[:, 1]

print("\n" + "=" * 58)
print("           CLASSIFICATION REPORT — FULL MODEL")
print("=" * 58)
print(classification_report(y_test, y_pred, target_names=["Flood", "Severe Flood"]))

metrics = {
    "Accuracy":  round(accuracy_score(y_test, y_pred),  4),
    "Precision": round(precision_score(y_test, y_pred), 4),
    "Recall":    round(recall_score(y_test, y_pred),    4),
    "F1":        round(f1_score(y_test, y_pred),        4),
    "ROC-AUC":   round(roc_auc_score(y_test, y_prob),   4),
}
for k, v in metrics.items():
    print(f"  {k:<12}: {v}")

cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_auc = cross_val_score(
    XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.04,
                  subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
                  scale_pos_weight=scale_pos, eval_metric='logloss',
                  random_state=42, verbosity=0),
    X_train_imp, y_train, cv=cv, scoring='roc_auc'
)
print(f"\n  5-Fold CV ROC-AUC: {cv_auc.mean():.4f} ± {cv_auc.std():.4f}")

imp = pd.Series(model.feature_importances_, index=ALL_FEATURES).sort_values()
top20 = imp.tail(20)

fig, ax = plt.subplots(figsize=(10, 8))
colors = ['#e07b54' if v >= imp.quantile(0.8) else '#5b8db8' for v in top20]
top20.plot(kind='barh', ax=ax, color=colors)
ax.set_title('XGBoost Top-20 Feature Importances — Full INDOFLOODS Model',
             fontsize=12, fontweight='bold', pad=12)
ax.set_xlabel('Importance Score')
ax.axvline(top20.mean(), color='grey', linestyle='--', linewidth=0.8, label='mean (top-20)')
ax.legend(fontsize=9)
plt.tight_layout()
plt.savefig(ARTIFACT_DIR / 'feature_importance_full.png', dpi=150)
plt.close()
print("\n✓ Feature importance plot saved")

cm = confusion_matrix(y_test, y_pred)
fig, ax = plt.subplots(figsize=(5, 4))
ax.imshow(cm, cmap='Blues')
ax.set_xticks([0,1]); ax.set_yticks([0,1])
ax.set_xticklabels(['Flood','Severe']); ax.set_yticklabels(['Flood','Severe'])
ax.set_xlabel('Predicted'); ax.set_ylabel('Actual')
ax.set_title('Confusion Matrix — Full Model')
for i in range(2):
    for j in range(2):
        ax.text(j, i, cm[i,j], ha='center', va='center',
                color='white' if cm[i,j] > cm.max()/2 else 'black', fontsize=14)
plt.tight_layout()
plt.savefig(ARTIFACT_DIR / 'confusion_matrix_full.png', dpi=150)
plt.close()
print("✓ Confusion matrix saved")

joblib.dump({
    'model':    model,
    'imputer':  imputer,
    'encoder':  encoder,
    'features': ALL_FEATURES,
    'cat_cols': CATCHMENT_CAT,
    'num_cols': ALL_NUM,
}, ARTIFACT_DIR / 'model_xgboost_full.pkl')
print("✓ model_xgboost_full.pkl saved")

sample_raw = X_test_imp.iloc[[0]]
prob = model.predict_proba(sample_raw)[0][1]
actual = "Severe Flood" if y_test.iloc[0] == 1 else "Flood"
print(f"\nSmoke test — Actual: {actual} | P(Severe Flood) = {prob:.2%}")
