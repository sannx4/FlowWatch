\# Raw Page Manifest Design



\## Purpose



FlowWatch must be able to identify the exact source page that entered an ingestion run

before business transformation occurs.



Day 11 introduces a page-level integrity manifest.



The manifest does not transform, normalize or canonicalize the source payload.



Instead, it computes SHA-256 over the exact response bytes preserved by the ingestion

client.



\## Processing order



```text

World Bank HTTP response

&#x20;       |

&#x20;       v

exact response bytes

&#x20;       |

&#x20;       v

SHA-256

&#x20;       |

&#x20;       v

raw\_page\_manifests

&#x20;       |

&#x20;       v

downstream validation / transformation

