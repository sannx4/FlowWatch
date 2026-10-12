\# Source Validation and Quarantine



\## Purpose



Day 12 introduces an explicit boundary between:



```text

raw source record

&#x20;     |

&#x20;     v

source parsing / schema validation

&#x20;     |

&#x20;     +---- invalid ----> rejected-record envelope

&#x20;     |

&#x20;     v

typed source record

&#x20;     |

&#x20;     v

later business transformation
