# Collection funnel

Denominator: 100; integrity: FAILED; saved: 0.
| Stage | Independent | Prefix | States |
|---|---:|---:|---|
| claimed | 100 | 100 | {"reached": 100} |
| first_frame | 70 | 70 | {"reached": 70, "failed": 30} |
| template_selected | 69 | 69 | {"reached": 69, "not_reached": 30, "unknown": 1} |
| model_http | 28 | 28 | {"not_reached": 72, "reached": 28} |
| initial_plan_accepted | 13 | 13 | {"unknown": 47, "not_reached": 30, "reached": 13, "failed": 10} |
| effective_steps_ge5 | 4 | 4 | {"unknown": 41, "not_reached": 30, "failed": 25, "reached": 4} |
| goal_verified | 0 | 0 | {"unknown": 70, "not_reached": 30} |
| formally_saved | 0 | 0 | {"unknown": 70, "not_reached": 30} |

Usage and per-candidate evidence are in funnel.json.

Issues: ["unsettled_claims"]

Saved mean input tokens: None; amortized input tokens: None

## Complete machine facts

```json
{
  "denominator": 100,
  "expected_denominator": 100,
  "site_denominators": {
    "app-692a94fed923f056a6a862fd": 3,
    "app-e3de3e48b34ab6788b7fd88c": 3,
    "app-69ff7af2ff194f3bd06fd4f7": 3,
    "app-9edd3238c39e0ec4f8ba2a4d": 3,
    "app-7997578ee50cd7f69091be58": 3,
    "app-a14a91aa44851afdd6775189": 3,
    "app-d533e3a4791e825199bf2c30": 3,
    "app-2534307b2632cec2f235901d": 3,
    "app-7fbe8bdae7a8b2ade139044b": 3,
    "app-e8ef9bc3028112bc32053886": 2,
    "app-dbc12c0fe08fee9b0d1e2ccf": 1,
    "app-636a2f32f6f61b737150de21": 3,
    "app-95f7633955f9037494bbe989": 3,
    "app-57e27368f9fb3d90ed521bf0": 3,
    "app-f5189cfa26c0bbd0f14c08b1": 3,
    "app-e79976782188a884e4e6d6fe": 3,
    "app-fc64872577d7c22f2d8b2bd0": 3,
    "app-758780c85e102a55d26755b7": 3,
    "app-72e259702360691d76096239": 3,
    "app-3759a408b490a1eec05b8ae0": 2,
    "app-ae9c4c62f5d1362f731e3873": 2,
    "app-0ffd0c8a72d9b9db3da6ca9d": 2,
    "app-d64d6954ab4483412bfb3d4a": 2,
    "app-bc9b5b27eb3c32f1774429d6": 2,
    "app-6cd7b65ba2ab7aa4639301be": 2,
    "app-f8047ab6666258671666046f": 2,
    "app-f26113b93443c5df3770b880": 2,
    "app-e8bb513049e5b87eab79a71d": 1,
    "app-470f2e6b8278a0fea9994c7e": 2,
    "app-dbf591b0fd48fd4985d99609": 2,
    "app-0fa00ada4df12cd3081de310": 2,
    "app-25078546eb12a715f8a3d1b8": 2,
    "app-a4d8cbe098478296fb4691a7": 2,
    "app-40761e8342e1bf94df5c7338": 2,
    "app-c4db227826711d6032e86727": 2,
    "app-d9bee133eb462ac25592ffcb": 2,
    "app-d9b9d3397a42bc56d35cd0ef": 2,
    "app-142addf092d49dad155909bf": 2,
    "app-31d149f04de3de94390a11ce": 2,
    "app-70f4eccb4c995840b01b098f": 1,
    "app-7bb632acb232d88045e1b659": 2,
    "app-2256b505c259ec4365c64594": 2,
    "app-98bb795629ae9e7d8271f984": 2
  },
  "expected_site_denominators": {
    "app-692a94fed923f056a6a862fd": 3,
    "app-e3de3e48b34ab6788b7fd88c": 3,
    "app-69ff7af2ff194f3bd06fd4f7": 3,
    "app-9edd3238c39e0ec4f8ba2a4d": 3,
    "app-7997578ee50cd7f69091be58": 3,
    "app-a14a91aa44851afdd6775189": 3,
    "app-d533e3a4791e825199bf2c30": 3,
    "app-2534307b2632cec2f235901d": 3,
    "app-7fbe8bdae7a8b2ade139044b": 3,
    "app-e8ef9bc3028112bc32053886": 2,
    "app-dbc12c0fe08fee9b0d1e2ccf": 1,
    "app-636a2f32f6f61b737150de21": 3,
    "app-95f7633955f9037494bbe989": 3,
    "app-57e27368f9fb3d90ed521bf0": 3,
    "app-f5189cfa26c0bbd0f14c08b1": 3,
    "app-e79976782188a884e4e6d6fe": 3,
    "app-fc64872577d7c22f2d8b2bd0": 3,
    "app-758780c85e102a55d26755b7": 3,
    "app-72e259702360691d76096239": 3,
    "app-3759a408b490a1eec05b8ae0": 2,
    "app-ae9c4c62f5d1362f731e3873": 2,
    "app-0ffd0c8a72d9b9db3da6ca9d": 2,
    "app-d64d6954ab4483412bfb3d4a": 2,
    "app-bc9b5b27eb3c32f1774429d6": 2,
    "app-6cd7b65ba2ab7aa4639301be": 2,
    "app-f8047ab6666258671666046f": 2,
    "app-f26113b93443c5df3770b880": 2,
    "app-e8bb513049e5b87eab79a71d": 1,
    "app-470f2e6b8278a0fea9994c7e": 2,
    "app-dbf591b0fd48fd4985d99609": 2,
    "app-0fa00ada4df12cd3081de310": 2,
    "app-25078546eb12a715f8a3d1b8": 2,
    "app-a4d8cbe098478296fb4691a7": 2,
    "app-40761e8342e1bf94df5c7338": 2,
    "app-c4db227826711d6032e86727": 2,
    "app-d9bee133eb462ac25592ffcb": 2,
    "app-d9b9d3397a42bc56d35cd0ef": 2,
    "app-142addf092d49dad155909bf": 2,
    "app-31d149f04de3de94390a11ce": 2,
    "app-70f4eccb4c995840b01b098f": 1,
    "app-7bb632acb232d88045e1b659": 2,
    "app-2256b505c259ec4365c64594": 2,
    "app-98bb795629ae9e7d8271f984": 2
  },
  "template_denominators": {
    "generic": 25,
    "unselected": 31,
    "operation": 40,
    "long_reading": 4
  },
  "stage_order": [
    "claimed",
    "first_frame",
    "template_selected",
    "model_http",
    "initial_plan_accepted",
    "effective_steps_ge5",
    "goal_verified",
    "formally_saved"
  ],
  "running_snapshot": false,
  "integrity": "FAILED",
  "issues": [
    "unsettled_claims"
  ],
  "funnel": {
    "claimed": {
      "independent": 100,
      "prefix": 100,
      "states": {
        "reached": 100
      },
      "top5_rejections": []
    },
    "first_frame": {
      "independent": 70,
      "prefix": 70,
      "states": {
        "reached": 70,
        "failed": 30
      },
      "top5_rejections": [
        {
          "code": "Error",
          "unique_candidates": 16,
          "events": 16
        },
        {
          "code": "CancelledError",
          "unique_candidates": 8,
          "events": 8
        },
        {
          "code": "EvidenceStale",
          "unique_candidates": 4,
          "events": 4
        },
        {
          "code": "ValueError",
          "unique_candidates": 1,
          "events": 1
        },
        {
          "code": "TimeoutError",
          "unique_candidates": 1,
          "events": 1
        }
      ]
    },
    "template_selected": {
      "independent": 69,
      "prefix": 69,
      "states": {
        "reached": 69,
        "not_reached": 30,
        "unknown": 1
      },
      "top5_rejections": []
    },
    "model_http": {
      "independent": 28,
      "prefix": 28,
      "states": {
        "not_reached": 72,
        "reached": 28
      },
      "top5_rejections": []
    },
    "initial_plan_accepted": {
      "independent": 13,
      "prefix": 13,
      "states": {
        "unknown": 47,
        "not_reached": 30,
        "reached": 13,
        "failed": 10
      },
      "top5_rejections": [
        {
          "code": "ACCEPTANCE_SOURCE_INVALID",
          "unique_candidates": 4,
          "events": 4
        },
        {
          "code": "BUSINESS_ROLE_CONFLICT",
          "unique_candidates": 3,
          "events": 3
        },
        {
          "code": "TARGET_BINDING_INVALID",
          "unique_candidates": 1,
          "events": 1
        },
        {
          "code": "RATIONALE_NOT_GROUNDED",
          "unique_candidates": 1,
          "events": 1
        },
        {
          "code": "EVIDENCE_ROUTE_INVALID",
          "unique_candidates": 1,
          "events": 1
        }
      ]
    },
    "effective_steps_ge5": {
      "independent": 4,
      "prefix": 4,
      "states": {
        "unknown": 41,
        "not_reached": 30,
        "failed": 25,
        "reached": 4
      },
      "top5_rejections": [
        {
          "code": "effective_steps_below_5",
          "unique_candidates": 25,
          "events": 25
        }
      ]
    },
    "goal_verified": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "unknown": 70,
        "not_reached": 30
      },
      "top5_rejections": []
    },
    "formally_saved": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "unknown": 70,
        "not_reached": 30
      },
      "top5_rejections": []
    }
  },
  "by_site": {
    "app-0fa00ada4df12cd3081de310": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 2
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          },
          {
            "code": "EvidenceStale",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-0ffd0c8a72d9b9db3da6ca9d": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "unknown": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-142addf092d49dad155909bf": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 1,
          "unknown": 1
        },
        "top5_rejections": [
          {
            "code": "ACCEPTANCE_SOURCE_INVALID",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 1,
          "unknown": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-2256b505c259ec4365c64594": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-25078546eb12a715f8a3d1b8": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "failed": 1,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "TimeoutError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-2534307b2632cec2f235901d": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 3
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 3,
            "events": 3
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-31d149f04de3de94390a11ce": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "ACCEPTANCE_SOURCE_INVALID",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-3759a408b490a1eec05b8ae0": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-40761e8342e1bf94df5c7338": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 1,
          "unknown": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-470f2e6b8278a0fea9994c7e": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "RATIONALE_NOT_GROUNDED",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-57e27368f9fb3d90ed521bf0": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "failed": 1,
          "unknown": 1,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "BUSINESS_ROLE_CONFLICT",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 2,
          "unknown": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 2,
            "events": 2
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      }
    },
    "app-636a2f32f6f61b737150de21": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      }
    },
    "app-692a94fed923f056a6a862fd": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 2,
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "failed": 1,
          "not_reached": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      }
    },
    "app-69ff7af2ff194f3bd06fd4f7": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "failed": 1,
          "reached": 2
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "not_reached": 1,
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-6cd7b65ba2ab7aa4639301be": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-70f4eccb4c995840b01b098f": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-72e259702360691d76096239": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 2,
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "EVIDENCE_ROUTE_INVALID",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      }
    },
    "app-758780c85e102a55d26755b7": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "unknown": 1,
          "reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 3
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 3,
            "events": 3
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      }
    },
    "app-7997578ee50cd7f69091be58": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "failed": 1,
          "unknown": 1
        },
        "top5_rejections": [
          {
            "code": "BUSINESS_ROLE_CONFLICT",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 2,
          "unknown": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 2,
            "events": 2
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      }
    },
    "app-7bb632acb232d88045e1b659": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "failed": 1,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-7fbe8bdae7a8b2ade139044b": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 3
        },
        "top5_rejections": [
          {
            "code": "EvidenceStale",
            "unique_candidates": 2,
            "events": 2
          },
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-95f7633955f9037494bbe989": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "failed": 1,
          "reached": 2
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "not_reached": 1,
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "not_reached": 1,
          "reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "failed": 1,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "TARGET_BINDING_INVALID",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "failed": 2
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 2,
            "events": 2
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-98bb795629ae9e7d8271f984": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "unknown": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 2
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 2,
            "events": 2
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-9edd3238c39e0ec4f8ba2a4d": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      }
    },
    "app-a14a91aa44851afdd6775189": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "not_reached": 1,
          "reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "unknown": 1,
          "failed": 1,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "ACCEPTANCE_SOURCE_INVALID",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "failed": 2
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 2,
            "events": 2
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      }
    },
    "app-a4d8cbe098478296fb4691a7": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 2
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          },
          {
            "code": "EvidenceStale",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-ae9c4c62f5d1362f731e3873": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "failed": 1,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-bc9b5b27eb3c32f1774429d6": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "failed": 1,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "ValueError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-c4db227826711d6032e86727": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 2
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 2,
            "events": 2
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-d533e3a4791e825199bf2c30": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "failed": 2,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 2,
            "events": 2
          }
        ]
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 2,
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 2,
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 2,
          "reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 2,
          "reached": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2,
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-d64d6954ab4483412bfb3d4a": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "ACCEPTANCE_SOURCE_INVALID",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-d9b9d3397a42bc56d35cd0ef": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      }
    },
    "app-d9bee133eb462ac25592ffcb": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-dbc12c0fe08fee9b0d1e2ccf": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-dbf591b0fd48fd4985d99609": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-e3de3e48b34ab6788b7fd88c": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 3
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 3,
            "events": 3
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-e79976782188a884e4e6d6fe": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      }
    },
    "app-e8bb513049e5b87eab79a71d": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-e8ef9bc3028112bc32053886": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      }
    },
    "app-f26113b93443c5df3770b880": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "BUSINESS_ROLE_CONFLICT",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-f5189cfa26c0bbd0f14c08b1": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 3
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 2,
            "events": 2
          },
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-f8047ab6666258671666046f": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-fc64872577d7c22f2d8b2bd0": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      }
    }
  },
  "by_template": {
    "generic": {
      "claimed": {
        "independent": 25,
        "prefix": 25,
        "states": {
          "reached": 25
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 25,
        "prefix": 25,
        "states": {
          "reached": 25
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 25,
        "prefix": 25,
        "states": {
          "reached": 25
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 7,
        "prefix": 7,
        "states": {
          "not_reached": 18,
          "reached": 7
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "unknown": 20,
          "failed": 4,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "ACCEPTANCE_SOURCE_INVALID",
            "unique_candidates": 2,
            "events": 2
          },
          {
            "code": "RATIONALE_NOT_GROUNDED",
            "unique_candidates": 1,
            "events": 1
          },
          {
            "code": "EVIDENCE_ROUTE_INVALID",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 18,
          "failed": 7
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 7,
            "events": 7
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 25
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 25
        },
        "top5_rejections": []
      }
    },
    "long_reading": {
      "claimed": {
        "independent": 4,
        "prefix": 4,
        "states": {
          "reached": 4
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 4,
        "prefix": 4,
        "states": {
          "reached": 4
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 4,
        "prefix": 4,
        "states": {
          "reached": 4
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "not_reached": 2,
          "reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "unknown": 3,
          "reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "unknown": 2,
          "failed": 1,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 4
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 4
        },
        "top5_rejections": []
      }
    },
    "operation": {
      "claimed": {
        "independent": 40,
        "prefix": 40,
        "states": {
          "reached": 40
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 40,
        "prefix": 40,
        "states": {
          "reached": 40
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 40,
        "prefix": 40,
        "states": {
          "reached": 40
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 19,
        "prefix": 19,
        "states": {
          "reached": 19,
          "not_reached": 21
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 11,
        "prefix": 11,
        "states": {
          "reached": 11,
          "unknown": 23,
          "failed": 6
        },
        "top5_rejections": [
          {
            "code": "BUSINESS_ROLE_CONFLICT",
            "unique_candidates": 3,
            "events": 3
          },
          {
            "code": "ACCEPTANCE_SOURCE_INVALID",
            "unique_candidates": 2,
            "events": 2
          },
          {
            "code": "TARGET_BINDING_INVALID",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "effective_steps_ge5": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "failed": 17,
          "unknown": 20,
          "reached": 3
        },
        "top5_rejections": [
          {
            "code": "effective_steps_below_5",
            "unique_candidates": 17,
            "events": 17
          }
        ]
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 40
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 40
        },
        "top5_rejections": []
      }
    },
    "unselected": {
      "claimed": {
        "independent": 31,
        "prefix": 31,
        "states": {
          "reached": 31
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "failed": 30,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 16,
            "events": 16
          },
          {
            "code": "CancelledError",
            "unique_candidates": 8,
            "events": 8
          },
          {
            "code": "EvidenceStale",
            "unique_candidates": 4,
            "events": 4
          },
          {
            "code": "ValueError",
            "unique_candidates": 1,
            "events": 1
          },
          {
            "code": "TimeoutError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 30,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 31
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 30,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 30,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 30,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 30,
          "unknown": 1
        },
        "top5_rejections": []
      }
    }
  },
  "faults": [
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "1d77afc4-1b31-4abd-8719-01e68c1beec9",
      "at": 1794962407.36674,
      "occurrence": 1,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "dc51bbd6-7803-4034-aa1c-d99c05a1790d",
      "at": 1794962408.063472,
      "occurrence": 2,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at axisScale (eval at evaluate (:370:30), <anonymous>:39:18)\n    at axisScale (eval at evaluate (:370:30), <anonymous>:39:18)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "f9f92ae7-eee3-4ede-8632-30abfac4d827",
      "at": 1794962422.078927,
      "occurrence": 3,
      "stop_dispatch": true
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1510:34)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "e32faa2e-915a-4c42-b61f-0e5007ef86ae",
      "at": 1794962429.5138922,
      "occurrence": 4,
      "stop_dispatch": true
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "5a7c68ef-a93f-4062-b743-0c6fb6c4decc",
      "at": 1794962432.860599,
      "occurrence": 5,
      "stop_dispatch": true
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794962470.070187,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963151.33674,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963152.0014038,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963262.435261,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963262.9418628,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.1703029,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.175943,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.264809,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.44782,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.5249228,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.549118,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.5499241,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "b520e426-2144-4392-b7b4-1299e49fdacb",
      "at": 1794963263.679745,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.048976,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.4228458,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.469192,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.624139,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.644471,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.778774,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.131252,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.161789,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.226815,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.302418,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.409102,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.4262578,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.528082,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.595592,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.697319,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1557:30)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "0d3cce26-7d1e-48fb-a62b-252f203bdde9",
      "at": 1794963273.5388339,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "199f1bc9-f237-4a59-9bd3-320f01850c2c",
      "at": 1794963278.053258,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963284.05361,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963284.6567092,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963284.730158,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963284.8911731,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963285.097377,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963285.314215,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963296.6257448,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963297.054327,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "6154de7c-7db5-4168-ab39-258ba3312f63",
      "at": 1794963297.143117,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1510:34)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "8edafc18-df9f-40b7-a8eb-bcfb661127af",
      "at": 1794963298.266423,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963305.408107,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.147605,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.440894,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.6164439,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.733407,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.7722082,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.948222,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963307.098762,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963307.503293,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963307.571852,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963307.730109,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963324.890219,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.397354,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.4181519,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "6154de7c-7db5-4168-ab39-258ba3312f63",
      "at": 1794963325.4317062,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.474896,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.500617,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.648742,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.658068,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.700288,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.846686,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.9529548,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.9751098,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963326.011752,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "b9ed25c6-b541-4362-9272-6a4603429e9f",
      "at": 1794963326.299642,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963332.317557,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963337.524906,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963337.96333,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963338.022321,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "b9ed25c6-b541-4362-9272-6a4603429e9f",
      "at": 1794963349.394512,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963385.336962,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963385.384081,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963385.558626,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963385.575708,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "error_feature": "webcollect.browser.EvidenceStale:browser.py:_capture:692",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "5b2aa771-efea-485a-af15-58776aaf4a45",
      "at": 1794963436.527309,
      "occurrence": 1,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "b9ed25c6-b541-4362-9272-6a4603429e9f",
      "at": 1794963441.0801249,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "页面同步观察超过15秒，停止该任务并保留检查点",
      "error_feature": "asyncio.exceptions.CancelledError:tasks.py:_wait:521",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "e5df7ea9-5342-42d7-9098-d46bef0002a3",
      "at": 1794963448.741078,
      "occurrence": 1,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "error_feature": "webcollect.browser.EvidenceStale:browser.py:_capture:692",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "4b6de7ba-91b6-4e18-a215-ecf0e9531c7b",
      "at": 1794963455.741327,
      "occurrence": 2,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963472.9499588,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "36176b7e-48e3-4e57-8d0a-e040efab37c2",
      "at": 1794963473.4091341,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963474.772036,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "eb045d64-0d15-477a-8e8e-32765897eb09",
      "at": 1794963518.325621,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963541.0461178,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963555.70512,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963555.750676,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963555.8197389,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963556.2529159,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963556.379483,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963556.4519758,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963556.93963,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.092198,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.171795,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.4282382,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.5889459,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.755873,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.763079,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.92367,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963558.299231,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963558.350934,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963558.5019689,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963558.747099,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963558.7794828,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.159892,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.2914188,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.330442,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.62626,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.677517,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.733484,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.9023721,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.942219,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963560.792575,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963561.153484,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963561.631289,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963561.805781,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963561.912488,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963562.371089,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963562.516682,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963562.5335739,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963562.955758,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963562.9714508,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963563.0037382,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963563.087048,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "3909246f-658d-486b-acd3-452c33b533eb",
      "at": 1794963563.104488,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154",
      "at": 1794963563.881693,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963564.008121,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963564.857676,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "3909246f-658d-486b-acd3-452c33b533eb",
      "at": 1794963565.260176,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963565.581964,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154",
      "at": 1794963566.035668,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963568.167819,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "3909246f-658d-486b-acd3-452c33b533eb",
      "at": 1794963568.362282,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154",
      "at": 1794963569.17362,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963570.3502479,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963571.465931,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963571.714855,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963573.863148,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "error_feature": "webcollect.browser.EvidenceStale:browser.py:_capture:692",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154",
      "at": 1794963574.471033,
      "occurrence": 3,
      "stop_dispatch": true
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963575.108425,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963575.6577542,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "unknown",
      "retry_count": 0,
      "disposition": "interrupted",
      "failure_class": null,
      "code": null,
      "reason": "SQLite retry stopped before lock acquisition",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154",
      "at": 1794963575.6686442,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963577.700245,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "network",
      "code": null,
      "reason": "Page.goto: net::ERR_EMPTY_RESPONSE at https://www.gdzwfw.gov.cn/\nCall log:\n  - navigating to \"https://www.gdzwfw.gov.cn/\", waiting until \"domcontentloaded\"\n",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "aa7d0723-3e03-4cee-99c7-1f051c58e107",
      "at": 1794964458.763325,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1560:134)\n    at Array.map (<anonymous>)\n    at eval (eval at evaluate (:370:30), <anonymous>:1560:106)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "e02de86e-c7b2-4b70-afe9-4650445254c6",
      "at": 1794964465.4449751,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "EOFError: ",
      "error_feature": "builtins.EOFError:connection.py:_recv:417",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "bfcba788-6004-4cc4-8247-8f56150654d8",
      "at": 1794964663.728781,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "EOFError: ",
      "error_feature": "builtins.EOFError:connection.py:_recv:417",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "58a0c976-c88f-45df-9e23-b8d4280cb2f1",
      "at": 1794964675.205211,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "network",
      "code": null,
      "reason": "Page.goto: net::ERR_CONNECTION_CLOSED at https://zh.wikipedia.org/wiki/Special:Random\nCall log:\n  - navigating to \"https://zh.wikipedia.org/wiki/Special:Random\", waiting until \"domcontentloaded\"\n",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "81d38088-19d1-4177-8785-3731f6da4a15",
      "at": 1794964689.539339,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "d6e5d7f8-36a1-458d-9a23-ee55da31d8d0",
      "at": 1794964705.875864,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "EOFError: ",
      "error_feature": "builtins.EOFError:connection.py:_recv:417",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "78703616-c7de-44e9-ab0c-968c7cc1e913",
      "at": 1794964732.041138,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "EOFError: ",
      "error_feature": "builtins.EOFError:connection.py:_recv:417",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "eabf65b3-952d-45ea-bf47-c6481e0a3ac1",
      "at": 1794964771.4411771,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "EOFError: ",
      "error_feature": "builtins.EOFError:connection.py:_recv:417",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "4fb5cf32-affb-42fd-8e9e-ed988e42a408",
      "at": 1794964797.945927,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "0fbe47a9-9c12-44a1-acde-95ab6c417906",
      "at": 1794964821.8624132,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "EOFError: ",
      "error_feature": "builtins.EOFError:connection.py:_recv:417",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "eb16a784-37d1-49bb-b057-c8b007138cf5",
      "at": 1794964828.351394,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "business",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "collector",
      "code": null,
      "reason": "单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "error_feature": "webcollect.browser.EvidenceStale:browser.py:_capture:693",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "cba11260-6b44-4d85-89fa-b1ee69a1a5a4",
      "at": 1794964856.926785,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "EOFError: ",
      "error_feature": "builtins.EOFError:connection.py:_recv:417",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "1ddd689e-c0e7-456c-b2f0-edd14ba3fe57",
      "at": 1794964875.634218,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "EOFError: ",
      "error_feature": "builtins.EOFError:connection.py:_recv:417",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "f08fd63d-6431-4b4e-8c3b-9b92702945e0",
      "at": 1794964879.0362082,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "HTTP_NAVIGATION_ENDPOINT_UNPROVEN",
      "error_feature": "builtins.ValueError:navigation.py:validate_http_chain:42",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "29d53c3c-5695-4ec6-b162-df1fb1740b25",
      "at": 1794965455.908463,
      "occurrence": 1,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "ValueError: bounded_plan_correction_failed: raw replies retained; no further correction dispatch",
      "error_feature": "builtins.ValueError:model_gateway.py:_call:1437",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "e8b0295d-3756-44ec-b971-f3a10d87c408",
      "at": 1794965659.70327,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "ValueError: bounded_field_repair_failed: patch retained; no further correction dispatch",
      "error_feature": "builtins.ValueError:model_gateway.py:_call:1435",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "757736b6-0a41-475d-9b6d-2fc9e8326500",
      "at": 1794965672.200572,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "3807030c-eb33-4958-8d51-0412a52fba5b",
      "at": 1794965674.229106,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "unknown",
      "retry_count": 0,
      "disposition": "interrupted",
      "failure_class": "interrupted",
      "code": null,
      "reason": "派发后结果未知（UNKNOWN），不自动补发：一次动作打开多个页面，需单独适配并记录",
      "error_feature": "builtins.ValueError:session_core.py:_perform_primitive:1695",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "dff49f92-6286-44d3-a748-7001d7f4a107",
      "at": 1794965739.377593,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "PLAN_ADMISSION_REJECTED: 验收范围须引用原目标原文",
      "error_feature": "webcollect.session_core.ReactStop:session.py:_first_plan_round:666",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "6467618f-0f98-4b8a-beb7-46ec461f03e3",
      "at": 1794965780.2881742,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "business",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "collector",
      "code": null,
      "reason": "NAVIGATION_SOURCE_UNPROVEN: destination has no exact permission",
      "error_feature": "webcollect.candidate_navigation.NavigationRejected:candidate_navigation.py:extend:159",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "7d69639a-6d48-4bb2-ad4d-c2e82f0b20ae",
      "at": 1794965796.222718,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "8a389e00-814a-4e21-82cd-a7e7a51fd909",
      "at": 1794965801.144054,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "PLAN_ADMISSION_REJECTED: process仅允许原目标明确要求的input/result过程及其原文来源；比较、最终结果与结论仍是outcome；CONTROL_TARGET_CONFLICT: e_4",
      "error_feature": "webcollect.session_core.ReactStop:session.py:_first_plan_round:666",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "ae2252fe-fdc2-431c-9ac0-6295842eb513",
      "at": 1794965810.1526499,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "PLAN_ADMISSION_REJECTED: FUTURE_TARGET_REQUIRES_SEMANTICS: use text/role/href, not a current control number；rationale中「」引用的界面文字必须逐字出现在当前帧可见文本（本步声明的输入或目标文本亦可）；用省略号拼接时每一段都要真实可见；尚未看到的页面只能写计划前提，不得断言其内容、焦点或选项；列表序号和角标数字由样式生成，不是可见文本，不要引用",
      "error_feature": "webcollect.session_core.ReactStop:session.py:_first_plan_round:666",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "7847ccb3-a024-4ac5-8843-b44422d7dfac",
      "at": 1794965859.303992,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "unknown",
      "retry_count": 0,
      "disposition": "interrupted",
      "failure_class": "interrupted",
      "code": null,
      "reason": "派发后结果未知（UNKNOWN），不自动补发：一次动作打开多个页面，需单独适配并记录",
      "error_feature": "builtins.ValueError:session_core.py:_perform_primitive:1695",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "2aa5301e-54a9-4aed-9f2a-771a50431abb",
      "at": 1794965915.9555268,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "business",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "collector",
      "code": null,
      "reason": "react_screenshot_raw_only:NO_PROGRESS_END:已访问的目标事实、有效证据和缺项状态反复回访，无进展结束",
      "error_feature": null,
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "cd307708-4723-445b-81d4-3a37e4aa0c3e",
      "at": 1794965936.8296719,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "unknown",
      "retry_count": 0,
      "disposition": "interrupted",
      "failure_class": "interrupted",
      "code": null,
      "reason": "CAPTURE_AFTER_ACTION_UNVERIFIED: 单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "error_feature": "webcollect.browser.EvidenceStale:browser.py:_capture:693",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "c6498f2d-055c-4fec-a7be-535d665787b4",
      "at": 1794965973.4184651,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "unknown",
      "retry_count": 0,
      "disposition": "interrupted",
      "failure_class": "interrupted",
      "code": null,
      "reason": "CAPTURE_AFTER_ACTION_UNVERIFIED: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1557:30)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "8459eef1-ce4b-400c-8235-c9ce6e9bbe5b",
      "at": 1794965997.382807,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "PLAN_ADMISSION_REJECTED: rationale中「」引用的界面文字必须逐字出现在当前帧可见文本（本步声明的输入或目标文本亦可）；用省略号拼接时每一段都要真实可见；尚未看到的页面只能写计划前提，不得断言其内容、焦点或选项；列表序号和角标数字由样式生成，不是可见文本，不要引用",
      "error_feature": "webcollect.session_core.ReactStop:session.py:_first_plan_round:661",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "4b64e716-2516-439f-bb9f-cd6af74eeae0",
      "at": 1794966018.829087,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "business",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "collector",
      "code": null,
      "reason": "react_screenshot_raw_only:NO_PROGRESS_END:相同业务事实、实际证据和缺项已询问且无新依据，保留原件并结束",
      "error_feature": null,
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "914c1e08-2813-4db7-ba01-96c26d238b01",
      "at": 1794966143.055779,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "business",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "collector",
      "code": null,
      "reason": "react_screenshot_raw_only:NO_PROGRESS_END:相同业务事实、实际证据和缺项已询问且无新依据，保留原件并结束",
      "error_feature": null,
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "87db16ad-44d1-4794-9f85-0d91ab695a48",
      "at": 1794966149.505565,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "PLAN_ADMISSION_REJECTED: r1:依赖未知事项或自身；r2:依赖未知事项或自身",
      "error_feature": "webcollect.session_core.ReactStop:session.py:_first_plan_round:661",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "d4484e61-c9e8-4bcb-8204-afdbb8286e9f",
      "at": 1794966188.15812,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "model",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "model",
      "code": null,
      "reason": "PLAN_ADMISSION_REJECTED: 验收范围须引用原目标原文",
      "error_feature": "webcollect.session_core.ReactStop:session.py:_first_plan_round:661",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "d215b09e-30a5-40c1-ad74-35fef0902814",
      "at": 1794966189.0509372,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "business",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "collector",
      "code": null,
      "reason": "react_screenshot_raw_only:NO_PROGRESS_END:已访问的目标事实、有效证据和缺项状态反复回访，无进展结束",
      "error_feature": null,
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "2f705b8c-588d-4865-8a8b-3eedd737a3bf",
      "at": 1794966234.813013,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "business",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "collector",
      "code": null,
      "reason": "react_screenshot_raw_only:NO_PROGRESS_END:已访问的目标事实、有效证据和缺项状态反复回访，无进展结束",
      "error_feature": null,
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "a08caec0-8a13-4789-8e20-e435bf663a7c",
      "at": 1794966294.039541,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "business",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": "collector",
      "code": null,
      "reason": "react_screenshot_raw_only:NO_PROGRESS_END:相同业务事实、实际证据和缺项已询问且无新依据，保留原件并结束",
      "error_feature": null,
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "7a6c8411-d162-499f-b7b1-f6ffc2843340",
      "at": 1794966466.694889,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "claim_id": "35c17913-93ed-4bb0-ac45-080b1ee9fb2f",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "199f1bc9-f237-4a59-9bd3-320f01850c2c",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "6154de7c-7db5-4168-ab39-258ba3312f63",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "d87908bd-e045-4e55-a598-898a08a14828",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "08a42126-7ce4-418c-9698-a4d87310da74",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "0d3cce26-7d1e-48fb-a62b-252f203bdde9",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1557:30)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "b9ed25c6-b541-4362-9272-6a4603429e9f",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "1cdf406f-4507-4cfd-a188-74c3cdf27bea",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "78f8755d-a78a-4baf-9e17-a2a446c8997c",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "74d2511e-0857-4fff-8129-e9f3503fcb27",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "12e4d392-8636-4b38-97fc-e7dbf4e38846",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "aa7d0723-3e03-4cee-99c7-1f051c58e107",
      "failure_class": null,
      "reason": "Error: Page.goto: net::ERR_EMPTY_RESPONSE at https://www.gdzwfw.gov.cn/\nCall log:\n  - navigating to \"https://www.gdzwfw.gov.cn/\", waiting until \"domcontentloaded\"\n",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "a885e82d-032b-452e-9823-fc6ebd0ab833",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "5cb69bde-f2e3-4205-9da8-c3e71180c8fb",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "4bd8565a-bc11-4ba3-ae25-88b2c51f8d93",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "cb359024-85da-4cbe-8db9-0a0d2517bed2",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "7988b049-2075-4ef6-8ffc-c85e337d07df",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "b520e426-2144-4392-b7b4-1299e49fdacb",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "baa0c71f-aeef-4842-a3cb-52626b01e9dc",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "29d53c3c-5695-4ec6-b162-df1fb1740b25",
      "failure_class": null,
      "reason": "ValueError: HTTP_NAVIGATION_ENDPOINT_UNPROVEN",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "a443b324-3c36-4279-92ba-74f0e7ff38de",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "97701ec9-07e5-4613-bda4-6a85a902c9a3",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "a7ccd2be-6f9c-42cb-ab73-2ef3b44ed8ec",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "349b292f-c6b7-4a4e-8e16-b4608824ae78",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "e5df7ea9-5342-42d7-9098-d46bef0002a3",
      "failure_class": null,
      "reason": "TimeoutError: 页面同步观察超过15秒，停止该任务并保留检查点",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "36176b7e-48e3-4e57-8d0a-e040efab37c2",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "0fbe47a9-9c12-44a1-acde-95ab6c417906",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "a2608120-9306-40ab-be0b-6f382f3f544d",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "aeaedf63-c90c-4925-bebf-ff9cfe9f88ca",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "6bea97e0-14f3-40f2-b782-3f90d9e3529d",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "ef6230c0-9566-457b-86d1-e11c43d2093d",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "5e105f46-7bb0-4dc8-8864-08eb5afd6d76",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "0af91db0-33ad-47ca-9657-c151f947cd58",
      "attempt_id": "34c095cd-85fe-400c-b9af-d6f5e916d1fc",
      "failure_class": "interrupted",
      "reason": "runner_cancelled",
      "disposition": "unclassified"
    },
    {
      "claim_id": "3807030c-eb33-4958-8d51-0412a52fba5b",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "a6841830-30bf-4e6a-9753-88a2d707a725",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "68185304-e686-4481-b21b-13f9d20bc01a",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "8a389e00-814a-4e21-82cd-a7e7a51fd909",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "1d77afc4-1b31-4abd-8719-01e68c1beec9",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "4b6de7ba-91b6-4e18-a215-ecf0e9531c7b",
      "failure_class": null,
      "reason": "EvidenceStale: 单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "eb045d64-0d15-477a-8e8e-32765897eb09",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "2175129c-7ef4-4b3c-a4e3-5f02fe7cfd62",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "c6ceb74c-f349-4f05-b197-39f260349dcb",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "8edafc18-df9f-40b7-a8eb-bcfb661127af",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1510:34)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "1c4fa4e9-e3e3-462d-a791-e56963efd2c3",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "aebd77de-87b9-46b4-aed1-dfb1a9e32bb4",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "f9f92ae7-eee3-4ede-8632-30abfac4d827",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at axisScale (eval at evaluate (:370:30), <anonymous>:39:18)\n    at axisScale (eval at evaluate (:370:30), <anonymous>:39:18)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "79608024-eeb4-4da4-ac39-be8260070222",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "5dad17bf-573c-4ab5-9afd-6af96546f45e",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "90972f16-623b-409f-b0d4-2a2d35e4a450",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "77af9c2a-971a-4810-9374-2a6c7e8a72bb",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "413d838d-b0c7-470a-9a3c-e2a4c1228451",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "f72c6ec8-f47d-4897-9291-a27ff217ca15",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "cba11260-6b44-4d85-89fa-b1ee69a1a5a4",
      "failure_class": null,
      "reason": "EvidenceStale: 单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "b9bfbb17-9376-4666-8f32-ee42b41f59f9",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "5a7c68ef-a93f-4062-b743-0c6fb6c4decc",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "920721b7-25b7-4f95-a29d-6edef302b7e4",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "e02de86e-c7b2-4b70-afe9-4650445254c6",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1560:134)\n    at Array.map (<anonymous>)\n    at eval (eval at evaluate (:370:30), <anonymous>:1560:106)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "905dfc40-4011-45e5-8e88-b23f4d388735",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "e44cd977-9d70-4813-9b7b-20493adc60df",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "e66f8390-d5cc-4660-9492-e904079e5efe",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "81d38088-19d1-4177-8785-3731f6da4a15",
      "failure_class": null,
      "reason": "Error: Page.goto: net::ERR_CONNECTION_CLOSED at https://zh.wikipedia.org/wiki/Special:Random\nCall log:\n  - navigating to \"https://zh.wikipedia.org/wiki/Special:Random\", waiting until \"domcontentloaded\"\n",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "d6e5d7f8-36a1-458d-9a23-ee55da31d8d0",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "cbf160f6-57bf-4350-af15-8a9799283983",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "d388e77b-6eb9-4266-b729-459a308c8118",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "baabcc08-6efd-4d93-a87b-3c0ced4106a7",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "dc51bbd6-7803-4034-aa1c-d99c05a1790d",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "5b2aa771-efea-485a-af15-58776aaf4a45",
      "failure_class": null,
      "reason": "EvidenceStale: 单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "3909246f-658d-486b-acd3-452c33b533eb",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "0399f563-2595-44ec-928d-177f41d17649",
      "attempt_id": "b59cab53-0c59-412b-867f-4b86c22b6115",
      "failure_class": "interrupted",
      "reason": "runner_cancelled",
      "disposition": "unclassified"
    },
    {
      "claim_id": "e32faa2e-915a-4c42-b61f-0e5007ef86ae",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1510:34)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "2e834a38-66d2-454f-82c6-5776001bdb52",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "532fae48-cdb4-43af-96f8-62e895ac28c7",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    }
  ],
  "fault_categories": {
    "page_program": 10,
    "transient": 132,
    "business": 35,
    "interrupted": 5,
    "unclassified": 72
  },
  "reason_owners": {
    "program": 142,
    "site": 11,
    "unknown": 77,
    "model": 16,
    "business": 8
  },
  "units": {
    "funnel": "unique frozen candidate",
    "requests": "unique physical request id",
    "tokens": "provider tokens",
    "elapsed": "seconds"
  },
  "usage": {
    "producer": {
      "requests": 317,
      "states": {
        "succeeded": 217,
        "invalid_response": 99,
        "reserved": 1
      },
      "dispatch": {
        "dispatched": 316,
        "unproven": 1
      },
      "input_tokens": null,
      "output_tokens": null,
      "known_input_tokens": 13295846,
      "known_output_tokens": 661345,
      "unknown_usage_requests": 1,
      "cost": "UNKNOWN"
    },
    "consumer": {
      "requests": 103,
      "states": {
        "succeeded": 83,
        "invalid_response": 20
      },
      "dispatch": {
        "dispatched": 103
      },
      "input_tokens": 2062007,
      "output_tokens": 76226,
      "known_input_tokens": 2062007,
      "known_output_tokens": 76226,
      "unknown_usage_requests": 0,
      "cost": "UNKNOWN"
    },
    "startup_probes": {
      "requests": 0,
      "states": {},
      "dispatch": {},
      "input_tokens": 0,
      "output_tokens": 0,
      "known_input_tokens": 0,
      "known_output_tokens": 0,
      "unknown_usage_requests": 0,
      "cost": "UNKNOWN"
    },
    "total": {
      "requests": 420,
      "states": {
        "succeeded": 300,
        "invalid_response": 119,
        "reserved": 1
      },
      "dispatch": {
        "dispatched": 419,
        "unproven": 1
      },
      "input_tokens": null,
      "output_tokens": null,
      "known_input_tokens": 15357853,
      "known_output_tokens": 737571,
      "unknown_usage_requests": 1,
      "cost": "UNKNOWN"
    }
  },
  "unattributed_requests": {
    "consumer": 2565,
    "startup_probes_scope_unknown": false,
    "producer": 1425
  },
  "saved": 0,
  "mean_saved_input_tokens": null,
  "amortized_input_tokens": null,
  "mean_saved_session_seconds": null,
  "mean_saved_output_tokens": null,
  "amortized_output_tokens": null,
  "amortized_session_seconds": null,
  "round_elapsed_seconds": 2991.680512750987,
  "cache_hits": 0,
  "web_visits": {
    "count": 99,
    "states": {
      "succeeded": 97,
      "failed": 2
    }
  },
  "tool_requests": {
    "count": 0,
    "states": {}
  },
  "candidates": [
    {
      "candidate_id": "candidate-375fd231-0d49-4cd5-b65d-c46182578840",
      "version": 1,
      "application_id": "app-692a94fed923f056a6a862fd",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "35c17913-93ed-4bb0-ac45-080b1ee9fb2f"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-01/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-01/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 135.25426420907024,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d44f1ec9-dd29-4cd2-a8db-91a05bb3fdf3",
      "version": 1,
      "application_id": "app-e3de3e48b34ab6788b7fd88c",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "199f1bc9-f237-4a59-9bd3-320f01850c2c"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-01/199f1bc9-f237-4a59-9bd3-320f01850c2c/first-observation-failure.json",
              "sha256": "0f99763daec7e551abb0c84bfaddd517a2561bdadf048e12b525e214b70cdfe8"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 141.88086867332458,
      "session_elapsed_seconds": 66.57329520804342,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-2976968d-59af-4881-b3ef-8ddcfc4a40e7",
      "version": 1,
      "application_id": "app-69ff7af2ff194f3bd06fd4f7",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "6154de7c-7db5-4168-ab39-258ba3312f63"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-01/6154de7c-7db5-4168-ab39-258ba3312f63/first-observation-failure.json",
              "sha256": "5d2f0bd57ea3f0371ac0b91a29fec6c05a2431502459128ad2de9646f5993ea1"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 278.96602691698354,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-a9b1993e-d240-461e-85e5-fba71bc7c07a",
      "version": 1,
      "application_id": "app-9edd3238c39e0ec4f8ba2a4d",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "d87908bd-e045-4e55-a598-898a08a14828"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-01/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-01/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 463.54788820794784,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-ae35d5a4-66ab-4b5e-a5dd-ae0fa8ab40db",
      "version": 1,
      "application_id": "app-7997578ee50cd7f69091be58",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "914c1e08-2813-4db7-ba01-96c26d238b01"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-01/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-01/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "3ac4de8693c54a97aeea047bdc9bbf78"
            },
            {
              "request_id": "f8c3bb6d3c3443eaa221f66e04a845ac"
            },
            {
              "request_id": "23f92e5d634d4a1a8a29beb9d6747ab5"
            },
            {
              "request_id": "87133b9c4d2a4173945a0375b217e270"
            },
            {
              "request_id": "3756e384272a46758cfeb247d997b632"
            },
            {
              "request_id": "a3abbdaeddc74a1b8d882614707fb780"
            },
            {
              "request_id": "aeb7df655ec34c0bb52dd7bd0fa0bf80"
            },
            {
              "request_id": "8aae7e7db75446b7b625cd3a229f5ac8"
            },
            {
              "request_id": "4c9e8bab0a0b46c3b1ae2ff1f6a1a838"
            },
            {
              "request_id": "add5044921a743daa0afe97928b14562"
            },
            {
              "request_id": "a701f0010bba4e6e9dfe52fd1e0f833f"
            },
            {
              "request_id": "9cb856d361fd4e2db3eba36a17f3185c"
            },
            {
              "request_id": "b744982fe33b4748ab015bdf4947c7d4"
            },
            {
              "request_id": "2e50e3c089f04be49a425f3907772c3f"
            },
            {
              "request_id": "30dbf2b3b4a645b7820285a7917a6428"
            },
            {
              "request_id": "eb3a7e5a1e414a01b1345060f83d3f9a"
            },
            {
              "request_id": "1fbf5a7faad64c80ba975abd27155c64"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-01/914c1e08-2813-4db7-ba01-96c26d238b01/execution/capture/evidence/S000053_sample_000038/raw/0009-screenshot-plan.json",
              "sha256": "edbd9e44e4a900b0a62c0d9994ea11cd52b7c87258afab726a0887a34a5067d8"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-01/914c1e08-2813-4db7-ba01-96c26d238b01/execution/capture/evidence/S000053_sample_000038/raw/raw-receipt.json",
              "sha256": "55da7b538dd616392a0716841243b2ecf003a277b3eacefb6748375630a2926e"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 724.1301920413971,
      "session_elapsed_seconds": 717.5668599160854,
      "effective_steps": 1,
      "first_request_plan_accepted": true,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-01/runtime.jsonl",
        "line": 13
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 17,
        "states": {
          "succeeded": 15,
          "invalid_response": 2
        },
        "dispatch": {
          "dispatched": 17
        },
        "input_tokens": 490969,
        "output_tokens": 11215,
        "known_input_tokens": 490969,
        "known_output_tokens": 11215,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d4c160c8-7db5-46b3-9dbf-9bf4420c4291",
      "version": 1,
      "application_id": "app-a14a91aa44851afdd6775189",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "08a42126-7ce4-418c-9698-a4d87310da74"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-02/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-02/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 135.85555441700853,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-89186119-bece-4542-88c4-a10a412fd270",
      "version": 1,
      "application_id": "app-d533e3a4791e825199bf2c30",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "0d3cce26-7d1e-48fb-a62b-252f203bdde9"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-02/0d3cce26-7d1e-48fb-a62b-252f203bdde9/first-observation-failure.json",
              "sha256": "cb3ad5e5d4f10ac317a09792aeff1c7a2c52ccccfa8b102c571a3dc911ba1bc7"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 136.07854008674622,
      "session_elapsed_seconds": 57.101450709044,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c8bccab8-e411-4a13-966a-c0003f61f8e3",
      "version": 1,
      "application_id": "app-2534307b2632cec2f235901d",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "b9ed25c6-b541-4362-9272-6a4603429e9f"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-02/b9ed25c6-b541-4362-9272-6a4603429e9f/first-observation-failure.json",
              "sha256": "03e318b2b7cf2bb7dea15fbc5a14766997ba97f1d357e4b3de8607e6da3e7c56"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 145.21357583999634,
      "session_elapsed_seconds": 63.141595375025645,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-420eb8bc-5d96-4680-ae3f-7c2873a55b5d",
      "version": 1,
      "application_id": "app-7fbe8bdae7a8b2ade139044b",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "1cdf406f-4507-4cfd-a188-74c3cdf27bea"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-02/1cdf406f-4507-4cfd-a188-74c3cdf27bea/first-observation-failure.json",
              "sha256": "a063ca21404f6210e88506e85462aad761fd556b4acdb60d968e9e26179e76c8"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 83.07121070800349,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-4550c5de-f539-446c-8576-8a0442f6cdf9",
      "version": 1,
      "application_id": "app-e8ef9bc3028112bc32053886",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "78f8755d-a78a-4baf-9e17-a2a446c8997c"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-02/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-02/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 460.0008916669758,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-b8f7717c-82a1-4fee-b924-5f4010e4fd1f",
      "version": 1,
      "application_id": "app-dbc12c0fe08fee9b0d1e2ccf",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "74d2511e-0857-4fff-8129-e9f3503fcb27"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-03/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-03/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 134.52666983392555,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-a9dd237d-5883-4a9c-9af3-6c28f7da4649",
      "version": 1,
      "application_id": "app-636a2f32f6f61b737150de21",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "12e4d392-8636-4b38-97fc-e7dbf4e38846"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-03/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-03/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 434.0599745409563,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-09333267-7f26-4e54-8631-5ed85b819f1d",
      "version": 1,
      "application_id": "app-95f7633955f9037494bbe989",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "aa7d0723-3e03-4cee-99c7-1f051c58e107"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-03/aa7d0723-3e03-4cee-99c7-1f051c58e107/first-observation-failure.json",
              "sha256": "d813900a9da12e22dfe73f95fb96f90443a6a33f58925786fbfc90c4133a145d"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 44.67847299575806,
      "session_elapsed_seconds": 22.56680662499275,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-736703cd-f6a0-4315-b700-31b775c1494c",
      "version": 1,
      "application_id": "app-57e27368f9fb3d90ed521bf0",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "1ddd689e-c0e7-456c-b2f0-edd14ba3fe57"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-03/runtime.jsonl",
              "line": 14
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-03/runtime.jsonl",
              "line": 16
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "624888cbc06f456dba166567a89efcec"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "failed",
          "code": "BUSINESS_ROLE_CONFLICT",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-03/runtime.jsonl",
              "line": 22
            }
          ],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-03/1ddd689e-c0e7-456c-b2f0-edd14ba3fe57/execution/capture/evidence/S000164_sample_000004/raw/raw-receipt.json",
              "sha256": "3e0b130341aeda6dc1eef528157dd4a71ccfac1144c205d8274794b9c9e5642c"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 406.9627547264099,
      "session_elapsed_seconds": 405.1677987090079,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 1,
        "states": {
          "succeeded": 1
        },
        "dispatch": {
          "dispatched": 1
        },
        "input_tokens": 26795,
        "output_tokens": 1286,
        "known_input_tokens": 26795,
        "known_output_tokens": 1286,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-3a31daf3-4f68-42e3-a112-b7d471e97f17",
      "version": 1,
      "application_id": "app-f5189cfa26c0bbd0f14c08b1",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "a885e82d-032b-452e-9823-fc6ebd0ab833"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-03/a885e82d-032b-452e-9823-fc6ebd0ab833/first-observation-failure.json",
              "sha256": "6f6f0d2110ae447e25236bc3dd31d2db7432e0ad07db82a1cbc2d27f874d6a6b"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 1.5194734159158543,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c79499d7-9232-4c7a-b01e-42839583f9d4",
      "version": 1,
      "application_id": "app-e79976782188a884e4e6d6fe",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "5cb69bde-f2e3-4205-9da8-c3e71180c8fb"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-04/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-04/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 130.70122954202816,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-05be67ef-2a34-49d0-8479-09a57a930278",
      "version": 1,
      "application_id": "app-fc64872577d7c22f2d8b2bd0",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "4bd8565a-bc11-4ba3-ae25-88b2c51f8d93"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-04/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-04/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 434.4001774999779,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c0182846-c964-40ed-9d1d-ed609a464878",
      "version": 1,
      "application_id": "app-758780c85e102a55d26755b7",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "78703616-c7de-44e9-ab0c-968c7cc1e913"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-04/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-04/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "113f59815d294defbafc17cf68ec89df"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-04/78703616-c7de-44e9-ab0c-968c7cc1e913/execution/capture/evidence/S000162_sample_000001/raw/raw-receipt.json",
              "sha256": "2241a92581d2dca5b42654071adae6119cdd06790e40de9cd28bbcb17f0b1e0a"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 311.67161321640015,
      "session_elapsed_seconds": 304.5968729999149,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 1,
        "states": {
          "invalid_response": 1
        },
        "dispatch": {
          "dispatched": 1
        },
        "input_tokens": 17575,
        "output_tokens": 814,
        "known_input_tokens": 17575,
        "known_output_tokens": 814,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-5e35114a-7106-42d7-b0ec-34b651c2523a",
      "version": 1,
      "application_id": "app-72e259702360691d76096239",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "cb359024-85da-4cbe-8db9-0a0d2517bed2"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-04/runtime.jsonl",
              "line": 23
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-04/runtime.jsonl",
              "line": 25
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 156.5499181660125,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-3c556361-c1a3-4acd-bac8-586a306a47a4",
      "version": 1,
      "application_id": "app-3759a408b490a1eec05b8ae0",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "a08caec0-8a13-4789-8e20-e435bf663a7c"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-04/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-04/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "e45059cce1104c04afd944425cacc51e"
            },
            {
              "request_id": "9dde850f76b246ac9878b805deda83ec"
            },
            {
              "request_id": "b963058cd85947aaa883c88aa01d83e9"
            },
            {
              "request_id": "a3f89a0c2480453289cd737418f6dff8"
            },
            {
              "request_id": "920f262c36e14e03a58df377036503a5"
            },
            {
              "request_id": "b7dda71b05444c06afad010adc1b2e1e"
            },
            {
              "request_id": "4c1871e2fcea46029633a8c7a2106be2"
            },
            {
              "request_id": "61f8ccfbb25d47199dacc54c79598276"
            },
            {
              "request_id": "a26dac931b6d492d82b42cfc74f24ed5"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-04/a08caec0-8a13-4789-8e20-e435bf663a7c/execution/capture/evidence/S000176_sample_000001/raw/0009-screenshot-plan.json",
              "sha256": "e4c9ba898a41315d36e80c341cd500ae967eefd269641854de250cf9fdc656f5"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "reached",
          "code": null,
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-04/a08caec0-8a13-4789-8e20-e435bf663a7c/execution/capture/evidence/S000176_sample_000001/raw/raw-receipt.json",
              "sha256": "b974ade7d4aa9117b4805bb05b14ee5a6c6bd8b3382c7e94940833d71b94c0ad"
            }
          ],
          "prefix_reached": true
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 870.2250969409943,
      "session_elapsed_seconds": 863.4521444999846,
      "effective_steps": 7,
      "first_request_plan_accepted": true,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-04/runtime.jsonl",
        "line": 13
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 9,
        "states": {
          "succeeded": 9
        },
        "dispatch": {
          "dispatched": 9
        },
        "input_tokens": 186205,
        "output_tokens": 3846,
        "known_input_tokens": 186205,
        "known_output_tokens": 3846,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-60146573-e1b6-4134-ae87-6f2ac5ac9ba6",
      "version": 1,
      "application_id": "app-ae9c4c62f5d1362f731e3873",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "7988b049-2075-4ef6-8ffc-c85e337d07df"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-05/7988b049-2075-4ef6-8ffc-c85e337d07df/first-observation-failure.json",
              "sha256": "79083408ec281eb598229f4b68bb8415813bce31dc798ce001580574f7d70389"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 123.5636615420226,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d201e34f-61b9-4262-8e0e-1af7d9a2201b",
      "version": 1,
      "application_id": "app-0ffd0c8a72d9b9db3da6ca9d",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "b520e426-2144-4392-b7b4-1299e49fdacb"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-05/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-05/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 441.2495462500956,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-a24b1534-e3e6-4dc4-9ee3-72dafffd7319",
      "version": 1,
      "application_id": "app-d64d6954ab4483412bfb3d4a",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "baa0c71f-aeef-4842-a3cb-52626b01e9dc"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-05/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-05/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 462.01941479195375,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-26f00cf8-d90c-478e-b7ee-be3fd352cd3d",
      "version": 1,
      "application_id": "app-bc9b5b27eb3c32f1774429d6",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "29d53c3c-5695-4ec6-b162-df1fb1740b25"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "ValueError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-05/29d53c3c-5695-4ec6-b162-df1fb1740b25/first-observation-failure.json",
              "sha256": "be2acaa19e8bd732945f51015310e4ead6df4d2ff7cac1cfe0ddced244568c22"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 35.49557304382324,
      "session_elapsed_seconds": 21.939224750036374,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c5a1a241-479c-46dd-98bc-f36e2cae4ce3",
      "version": 1,
      "application_id": "app-6cd7b65ba2ab7aa4639301be",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "87db16ad-44d1-4794-9f85-0d91ab695a48"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-05/runtime.jsonl",
              "line": 14
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-05/runtime.jsonl",
              "line": 16
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "04defee68ab2487bbebcb4374003306b"
            },
            {
              "request_id": "2200b04e66c648e1b59e7ccb9d840aa5"
            },
            {
              "request_id": "61fa16f149f84701a550d426496b5481"
            },
            {
              "request_id": "95559a6ce78642eeaa207ad8de3f3198"
            },
            {
              "request_id": "344103fd216440f3af7ae2334b6c8748"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-05/87db16ad-44d1-4794-9f85-0d91ab695a48/execution/capture/evidence/S000190_sample_000001/raw/0013-screenshot-plan.json",
              "sha256": "edcab29b721c5e56de74451d288d69ef83cf2c6e34980c67b6c91c04a66ec6d8"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "reached",
          "code": null,
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-05/87db16ad-44d1-4794-9f85-0d91ab695a48/execution/capture/evidence/S000190_sample_000001/raw/raw-receipt.json",
              "sha256": "fa40a2020f43161d0b6ef438837dfac14bc82e842f98283089706f3ad2a09490"
            }
          ],
          "prefix_reached": true
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 687.7717840671539,
      "session_elapsed_seconds": 686.3006482919445,
      "effective_steps": 6,
      "first_request_plan_accepted": false,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-05/runtime.jsonl",
        "line": 24
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 5,
        "states": {
          "succeeded": 5
        },
        "dispatch": {
          "dispatched": 5
        },
        "input_tokens": 84789,
        "output_tokens": 3007,
        "known_input_tokens": 84789,
        "known_output_tokens": 3007,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-ec31078c-f737-408b-a746-358a73a083ed",
      "version": 1,
      "application_id": "app-f8047ab6666258671666046f",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "a443b324-3c36-4279-92ba-74f0e7ff38de"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-06/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-06/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 117.87452320801094,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c3b8e1de-61cc-4d42-946c-d8fac99f513d",
      "version": 1,
      "application_id": "app-f26113b93443c5df3770b880",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "97701ec9-07e5-4613-bda4-6a85a902c9a3"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-06/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-06/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 431.25271695898846,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-b42da83e-8934-4deb-9115-74b1a2206ce5",
      "version": 1,
      "application_id": "app-e8bb513049e5b87eab79a71d",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "bfcba788-6004-4cc4-8247-8f56150654d8"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-06/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-06/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "0adb2da960244cf49f7c4c8527e4bf5b"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-06/bfcba788-6004-4cc4-8247-8f56150654d8/execution/capture/evidence/S000184_sample_000001/raw/raw-receipt.json",
              "sha256": "9efd23f816bf3203fe6e100f00b6e47760005aaa471131cfea209b0563ac5147"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 239.65180802345276,
      "session_elapsed_seconds": 233.83042520901654,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 1,
        "states": {
          "invalid_response": 1
        },
        "dispatch": {
          "dispatched": 1
        },
        "input_tokens": 11624,
        "output_tokens": 1478,
        "known_input_tokens": 11624,
        "known_output_tokens": 1478,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-349828b7-d8cd-4595-a312-07562dc6d962",
      "version": 1,
      "application_id": "app-470f2e6b8278a0fea9994c7e",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "a7ccd2be-6f9c-42cb-ab73-2ef3b44ed8ec"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-06/runtime.jsonl",
              "line": 23
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-06/runtime.jsonl",
              "line": 25
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 220.68275799998082,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-17427055-f5a9-4984-90d6-c7325cf052bf",
      "version": 1,
      "application_id": "app-dbf591b0fd48fd4985d99609",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "2f705b8c-588d-4865-8a8b-3eedd737a3bf"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-06/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-06/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "1d888455dfaf4b9fa4958efe12464dc4"
            },
            {
              "request_id": "d64942e4bba446868b27b8ae5f2ad3f7"
            },
            {
              "request_id": "95eaf84cc90f4ff1a741b251ef7a6804"
            },
            {
              "request_id": "e14c4457551048af881b087d932799a8"
            },
            {
              "request_id": "f24390cfa7be4c57ba83377f7e8771c5"
            },
            {
              "request_id": "87236c636feb4a37a9407205ee72fe00"
            },
            {
              "request_id": "99308fbe2d9a4f98b844ea8a84a0abd4"
            },
            {
              "request_id": "b951928d5eb0485c8ea692be1a2f998e"
            },
            {
              "request_id": "1da9def6dd04488b8c6feabb6f5c0187"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-06/2f705b8c-588d-4865-8a8b-3eedd737a3bf/execution/capture/evidence/S000170_sample_000001/raw/0015-screenshot-plan.json",
              "sha256": "0396e7bf93557a5fb5fab90ca5e45f7dce4517db8da15c7fe0c947e8000bcc99"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "reached",
          "code": null,
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-06/2f705b8c-588d-4865-8a8b-3eedd737a3bf/execution/capture/evidence/S000170_sample_000001/raw/raw-receipt.json",
              "sha256": "8fca2181a4d0da4c1355a589da9bdbf0bd6a62cdcd346720d0348e32fae90b82"
            }
          ],
          "prefix_reached": true
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 809.9334201812744,
      "session_elapsed_seconds": 799.6049831249984,
      "effective_steps": 7,
      "first_request_plan_accepted": false,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-06/runtime.jsonl",
        "line": 15
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 9,
        "states": {
          "succeeded": 9
        },
        "dispatch": {
          "dispatched": 9
        },
        "input_tokens": 257612,
        "output_tokens": 7657,
        "known_input_tokens": 257612,
        "known_output_tokens": 7657,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-6e6d4a28-95bf-43e8-b368-c29bd5587b0a",
      "version": 1,
      "application_id": "app-0fa00ada4df12cd3081de310",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "349b292f-c6b7-4a4e-8e16-b4608824ae78"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-07/349b292f-c6b7-4a4e-8e16-b4608824ae78/first-observation-failure.json",
              "sha256": "2e2b868761a1ee95496d9d60f441713e5b4d87b55750469f2077bcd73a541f2c"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 137.18654583301395,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-79dfd883-f765-484f-9975-9c48f386f4be",
      "version": 1,
      "application_id": "app-25078546eb12a715f8a3d1b8",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "e5df7ea9-5342-42d7-9098-d46bef0002a3"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "TimeoutError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-07/e5df7ea9-5342-42d7-9098-d46bef0002a3/first-observation-failure.json",
              "sha256": "2f526bcb1bc0313f3ab26ed43141b09ca120f9f485eb5e71dc47be1cb767f7ad"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 232.2881142909173,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-8925f228-1c19-4059-9e8b-dd65cc52379d",
      "version": 1,
      "application_id": "app-a4d8cbe098478296fb4691a7",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "36176b7e-48e3-4e57-8d0a-e040efab37c2"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-07/36176b7e-48e3-4e57-8d0a-e040efab37c2/first-observation-failure.json",
              "sha256": "a030577ff8181d54abb5999e8a35578ec15d7e6a3c64490e412b9f9125c33ed1"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 82.40674754104111,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-5110f7b6-65e1-4dd0-8fa4-2e38d012dceb",
      "version": 1,
      "application_id": "app-40761e8342e1bf94df5c7338",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "4fb5cf32-affb-42fd-8e9e-ed988e42a408"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-07/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-07/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "c4dffd3071fe428f84d1a0834d4aacf2"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-07/4fb5cf32-affb-42fd-8e9e-ed988e42a408/execution/capture/evidence/S000206_sample_000001/raw/raw-receipt.json",
              "sha256": "439ef659d2ec7bc39ae936381ee65819c118d373aed1db5b1aa79f72538a5782"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 377.14063787460327,
      "session_elapsed_seconds": 372.45209387503564,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 1,
        "states": {
          "invalid_response": 1
        },
        "dispatch": {
          "dispatched": 1
        },
        "input_tokens": 12673,
        "output_tokens": 1590,
        "known_input_tokens": 12673,
        "known_output_tokens": 1590,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-103dfbff-5206-46e7-983d-f4d87437fba6",
      "version": 1,
      "application_id": "app-c4db227826711d6032e86727",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "0fbe47a9-9c12-44a1-acde-95ab6c417906"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-07/0fbe47a9-9c12-44a1-acde-95ab6c417906/first-observation-failure.json",
              "sha256": "d5d69bbc3215b987d2c8c8a604ef5fa4582c3ba9387ad173d7e59fe99e836cd5"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 17.7215256690979,
      "session_elapsed_seconds": 10.72255458298605,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-46f027af-b010-4e67-b3d7-66f6a1c639ab",
      "version": 1,
      "application_id": "app-d9bee133eb462ac25592ffcb",
      "template": "long_reading",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "a2608120-9306-40ab-be0b-6f382f3f544d"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-08/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-08/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 124.98788816703018,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-e1979b2d-6c92-496f-8084-e98cd5aef88c",
      "version": 1,
      "application_id": "app-d9b9d3397a42bc56d35cd0ef",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "aeaedf63-c90c-4925-bebf-ff9cfe9f88ca"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-08/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-08/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 411.5707942500012,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-1e0661d8-89dd-4819-9bcd-be2ceb510c4a",
      "version": 1,
      "application_id": "app-142addf092d49dad155909bf",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "eabf65b3-952d-45ea-bf47-c6481e0a3ac1"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-08/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-08/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "f9b0ab0e3ed9433ba95cd9cc8572e4ff"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "failed",
          "code": "ACCEPTANCE_SOURCE_INVALID",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-08/runtime.jsonl",
              "line": 13
            }
          ],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-08/eabf65b3-952d-45ea-bf47-c6481e0a3ac1/execution/capture/evidence/S000246_sample_000001/raw/raw-receipt.json",
              "sha256": "f6f0e1d566f2c09a18e995c215ad68c9667fcaf90ac4ab4140add96e65f70a67"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 347.7495050430298,
      "session_elapsed_seconds": 339.18109924998134,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 1,
        "states": {
          "succeeded": 1
        },
        "dispatch": {
          "dispatched": 1
        },
        "input_tokens": 16897,
        "output_tokens": 1194,
        "known_input_tokens": 16897,
        "known_output_tokens": 1194,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-f6e47429-ed83-4dc5-9f96-f75bbb0efb9f",
      "version": 1,
      "application_id": "app-31d149f04de3de94390a11ce",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "6bea97e0-14f3-40f2-b782-3f90d9e3529d"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-08/runtime.jsonl",
              "line": 25
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-08/runtime.jsonl",
              "line": 27
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 117.30919595796149,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-6529c885-7105-4744-b748-d0d4001993fb",
      "version": 1,
      "application_id": "app-70f4eccb4c995840b01b098f",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "7d69639a-6d48-4bb2-ad4d-c2e82f0b20ae"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-08/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-08/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "97d9348b54684012ae113b2bc95381ec"
            },
            {
              "request_id": "e87c861bb73347a3a425919902ee77c5"
            },
            {
              "request_id": "4fef634f9cea442c88a73c73c36fee22"
            },
            {
              "request_id": "0db389cca9f44748997c28388ef33405"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-08/7d69639a-6d48-4bb2-ad4d-c2e82f0b20ae/execution/capture/evidence/S000251_sample_000001/raw/0013-screenshot-plan.json",
              "sha256": "9e06d5588350450e5e8c71de54a215927a1dea461e17fd38fa75391311fd09e0"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-08/7d69639a-6d48-4bb2-ad4d-c2e82f0b20ae/execution/capture/evidence/S000251_sample_000001/raw/raw-receipt.json",
              "sha256": "6c3b590a926f08a78490721ffd2798c235caf2594a20302d6966da7c74dab57f"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 368.06187891960144,
      "session_elapsed_seconds": 360.3641187920002,
      "effective_steps": 2,
      "first_request_plan_accepted": false,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-08/runtime.jsonl",
        "line": 15
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 4,
        "states": {
          "succeeded": 3,
          "invalid_response": 1
        },
        "dispatch": {
          "dispatched": 4
        },
        "input_tokens": 90323,
        "output_tokens": 2885,
        "known_input_tokens": 90323,
        "known_output_tokens": 2885,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-5eb6a109-4072-45ea-9777-04ab4b5cefcb",
      "version": 1,
      "application_id": "app-7bb632acb232d88045e1b659",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "ef6230c0-9566-457b-86d1-e11c43d2093d"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-09/ef6230c0-9566-457b-86d1-e11c43d2093d/first-observation-failure.json",
              "sha256": "62228a7d8cdb3229c0970b7a5c50647cc28b21419038e57389d6fc96b4d2b2cb"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 131.65656024997588,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-b16312a7-648d-4d6e-a204-5fd93e9bffb0",
      "version": 1,
      "application_id": "app-2256b505c259ec4365c64594",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "5e105f46-7bb0-4dc8-8864-08eb5afd6d76"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-09/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-09/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 434.898493124987,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-65629fca-6ce0-4175-9fe0-098221f52915",
      "version": 1,
      "application_id": "app-98bb795629ae9e7d8271f984",
      "template": "operation",
      "template_source": "site_rule",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "0af91db0-33ad-47ca-9657-c151f947cd58"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-09/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-09/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-09/0af91db0-33ad-47ca-9657-c151f947cd58/execution/capture/evidence/S000001_sample_000198/raw/raw-receipt.json",
              "sha256": "0a98b54e3cec8bdaf0c20fff4609641707a5c6f9861ab57fb62ef187d295e68d"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 466.1736414170591,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-4242ca9c-e23c-4219-bd2b-6a7ecfc40b84",
      "version": 1,
      "application_id": "app-692a94fed923f056a6a862fd",
      "template": "long_reading",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "e8b0295d-3756-44ec-b971-f3a10d87c408"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-09/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-09/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "a905eb81f16748c49121587a835b1c62"
            },
            {
              "request_id": "c39b94d4a62d4f3e9bd32c6a24994974"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-09/e8b0295d-3756-44ec-b971-f3a10d87c408/execution/capture/evidence/S000002_sample_000191/raw/raw-receipt.json",
              "sha256": "9305eb2dfdccf2547a2ebc104ef44aef7475e4eafb5c8ce1aa4e338aca36d673"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 244.66658210754395,
      "session_elapsed_seconds": 238.9842236250406,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 2,
        "states": {
          "invalid_response": 2
        },
        "dispatch": {
          "dispatched": 2
        },
        "input_tokens": 31746,
        "output_tokens": 2098,
        "known_input_tokens": 31746,
        "known_output_tokens": 2098,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-78befcac-eb64-46f7-8c94-66a4b772383b",
      "version": 1,
      "application_id": "app-e3de3e48b34ab6788b7fd88c",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "3807030c-eb33-4958-8d51-0412a52fba5b"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-09/3807030c-eb33-4958-8d51-0412a52fba5b/first-observation-failure.json",
              "sha256": "485c573f720d64dead281a05136a23efca2382b44fa8ca260df4a3f5816df32d"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 12.947925090789795,
      "session_elapsed_seconds": 5.57349212502595,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-f9857de6-6f63-4ba5-b9cd-04cc9db131d4",
      "version": 1,
      "application_id": "app-69ff7af2ff194f3bd06fd4f7",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "a6841830-30bf-4e6a-9753-88a2d707a725"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-10/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-10/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 134.65049554104917,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-ccd4bf5b-0bec-4102-924a-b2861fd99d53",
      "version": 1,
      "application_id": "app-9edd3238c39e0ec4f8ba2a4d",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "68185304-e686-4481-b21b-13f9d20bc01a"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-10/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-10/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 432.0335450830171,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-96ce87ee-2cdb-4662-a9ad-3246904f1ece",
      "version": 1,
      "application_id": "app-7997578ee50cd7f69091be58",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "f08fd63d-6431-4b4e-8c3b-9b92702945e0"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-10/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-10/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "b574750b3cf745ecaf86810765e31e3f"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "failed",
          "code": "BUSINESS_ROLE_CONFLICT",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-10/runtime.jsonl",
              "line": 13
            }
          ],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-10/f08fd63d-6431-4b4e-8c3b-9b92702945e0/execution/capture/evidence/S000053_sample_000037/raw/raw-receipt.json",
              "sha256": "e31bde945982c268be4a7931756924066045d2eb8b629d013a72a30f3382c726"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 461.484503030777,
      "session_elapsed_seconds": 454.0214714159956,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 1,
        "states": {
          "succeeded": 1
        },
        "dispatch": {
          "dispatched": 1
        },
        "input_tokens": 14710,
        "output_tokens": 1233,
        "known_input_tokens": 14710,
        "known_output_tokens": 1233,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-adc5f986-a041-4a3a-ae89-f5e3005b6716",
      "version": 1,
      "application_id": "app-a14a91aa44851afdd6775189",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "6467618f-0f98-4b8a-beb7-46ec461f03e3"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-10/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-10/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "79ce35d81595407ebb5812c0beb57592"
            },
            {
              "request_id": "575509ccaefc4b3da4fc14bc6103d62a"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "failed",
          "code": "ACCEPTANCE_SOURCE_INVALID",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-10/runtime.jsonl",
              "line": 15
            }
          ],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-10/6467618f-0f98-4b8a-beb7-46ec461f03e3/execution/capture/evidence/S000027_sample_000002/raw/raw-receipt.json",
              "sha256": "2a72ee00d26ee16f14463ae4b30878ada815d0839ad9048e1260a80eb5c57cd3"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 364.7940547466278,
      "session_elapsed_seconds": 358.5991237499984,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 2,
        "states": {
          "succeeded": 2
        },
        "dispatch": {
          "dispatched": 2
        },
        "input_tokens": 50395,
        "output_tokens": 1690,
        "known_input_tokens": 50395,
        "known_output_tokens": 1690,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-0937c35c-26c7-454e-8b5b-2376aea5e73f",
      "version": 1,
      "application_id": "app-d533e3a4791e825199bf2c30",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "8a389e00-814a-4e21-82cd-a7e7a51fd909"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-10/8a389e00-814a-4e21-82cd-a7e7a51fd909/first-observation-failure.json",
              "sha256": "0b8a31396950b0c12b3eddd49c9f893198b5f6b157e6c950c6d9bef78446c412"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 19.2691912651062,
      "session_elapsed_seconds": 11.111696959007531,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-3bf907ee-906b-4412-92f5-022725fff53d",
      "version": 1,
      "application_id": "app-2534307b2632cec2f235901d",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "1d77afc4-1b31-4abd-8719-01e68c1beec9"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-11/1d77afc4-1b31-4abd-8719-01e68c1beec9/first-observation-failure.json",
              "sha256": "6ce4cf4cf7a8740f052e618e19a09ba31250de14bf7b572ae861fdbf6a91f7cc"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 116.70210695266724,
      "session_elapsed_seconds": 60.06035499996506,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-be57fa9e-87eb-467e-9798-0f44c73d6216",
      "version": 1,
      "application_id": "app-7fbe8bdae7a8b2ade139044b",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "4b6de7ba-91b6-4e18-a215-ecf0e9531c7b"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "EvidenceStale",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-11/4b6de7ba-91b6-4e18-a215-ecf0e9531c7b/first-observation-failure.json",
              "sha256": "a2297e264569effc30cd743114ff7f80ac782ead8f5e9d17da22f25614c63acc"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 321.0930471420288,
      "session_elapsed_seconds": 257.31809737498406,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-a7a8b472-d803-4e92-b5df-cdccad9a1fa9",
      "version": 1,
      "application_id": "app-e8ef9bc3028112bc32053886",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "eb045d64-0d15-477a-8e8e-32765897eb09"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-11/eb045d64-0d15-477a-8e8e-32765897eb09/first-observation-failure.json",
              "sha256": "f0fabd7c3ffae1909e232de7b5e140558d8f46693798ec279483ce41d1f9be8e"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 82.50402729108464,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-f5c4f5df-af7d-4e90-9a38-57694392d771",
      "version": 1,
      "application_id": "app-636a2f32f6f61b737150de21",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "2175129c-7ef4-4b3c-a4e3-5f02fe7cfd62"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-11/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-11/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 464.42620529211126,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-5e7ebee4-fe98-4799-8bd2-610a05e29b48",
      "version": 1,
      "application_id": "app-95f7633955f9037494bbe989",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "7847ccb3-a024-4ac5-8843-b44422d7dfac"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-11/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-11/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "e3212b65e86246acb69e5a5d43b82d0c"
            },
            {
              "request_id": "1c73a6d578684f9b859ba151ab121399"
            },
            {
              "request_id": "11b7aaf470f1492593b0f475c362b3aa"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "failed",
          "code": "TARGET_BINDING_INVALID",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-11/runtime.jsonl",
              "line": 15
            }
          ],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-11/7847ccb3-a024-4ac5-8843-b44422d7dfac/execution/capture/evidence/S000048_sample_000002/raw/raw-receipt.json",
              "sha256": "49874806add1aba987c5ed952263fab7763a1e22e5218a4e552a3ba6860551ba"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 442.1916980743408,
      "session_elapsed_seconds": 434.96668524993584,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 3,
        "states": {
          "succeeded": 2,
          "invalid_response": 1
        },
        "dispatch": {
          "dispatched": 3
        },
        "input_tokens": 44299,
        "output_tokens": 3329,
        "known_input_tokens": 44299,
        "known_output_tokens": 3329,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-6807133c-a054-4369-950e-7ffd52a74240",
      "version": 1,
      "application_id": "app-57e27368f9fb3d90ed521bf0",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "c6ceb74c-f349-4f05-b197-39f260349dcb"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-12/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-12/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 132.1373826659983,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-5476dfbe-afe9-4fcf-98d0-c858584d5a08",
      "version": 1,
      "application_id": "app-f5189cfa26c0bbd0f14c08b1",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "8edafc18-df9f-40b7-a8eb-bcfb661127af"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-12/8edafc18-df9f-40b7-a8eb-bcfb661127af/first-observation-failure.json",
              "sha256": "826312ab9361e13a080defcceaea14d52efa0263d19a6cf6dcd1fc524ef3a7f5"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 146.7670979499817,
      "session_elapsed_seconds": 81.84340641694143,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-aa9fc6ea-024f-41f8-a848-90113487172c",
      "version": 1,
      "application_id": "app-e79976782188a884e4e6d6fe",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "1c4fa4e9-e3e3-462d-a791-e56963efd2c3"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-12/runtime.jsonl",
              "line": 14
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-12/runtime.jsonl",
              "line": 16
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 224.40358724992257,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-eaae91a3-e828-4532-8df5-335fe9528901",
      "version": 1,
      "application_id": "app-fc64872577d7c22f2d8b2bd0",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "aebd77de-87b9-46b4-aed1-dfb1a9e32bb4"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-12/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-12/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 458.2786567909643,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-3b68cc32-3a66-4903-a0fd-dfe9a7acff8e",
      "version": 1,
      "application_id": "app-758780c85e102a55d26755b7",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "dff49f92-6286-44d3-a748-7001d7f4a107"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-12/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-12/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "b2ae455d1698421fb507a8098944fe4d"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-12/dff49f92-6286-44d3-a748-7001d7f4a107/execution/capture/evidence/S000162_sample_000002/raw/0009-screenshot-plan.json",
              "sha256": "7bcb55dc5d60ba0b739b97f02640371169aa6c73b724f2b02dd7b40eef30be2c"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-12/dff49f92-6286-44d3-a748-7001d7f4a107/execution/capture/evidence/S000162_sample_000002/raw/raw-receipt.json",
              "sha256": "d4248ca93788f56c4dd0a779695b3ff4cfa00b7b96651f1e990006bdba6e06b1"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 303.7875632500509,
      "effective_steps": 2,
      "first_request_plan_accepted": true,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-12/runtime.jsonl",
        "line": 13
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 1,
        "states": {
          "succeeded": 1
        },
        "dispatch": {
          "dispatched": 1
        },
        "input_tokens": 15374,
        "output_tokens": 938,
        "known_input_tokens": 15374,
        "known_output_tokens": 938,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-bdafa2fc-357a-4919-b516-962efb579911",
      "version": 1,
      "application_id": "app-72e259702360691d76096239",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "f9f92ae7-eee3-4ede-8632-30abfac4d827"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-13/f9f92ae7-eee3-4ede-8632-30abfac4d827/first-observation-failure.json",
              "sha256": "fa18134ab256d305739879221beea419828d8d7e622c069b165eac255e19fdcf"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 123.28526592254639,
      "session_elapsed_seconds": 70.32241870788857,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-add30cf0-8ea5-4f86-9e07-d3bb8d8e0372",
      "version": 1,
      "application_id": "app-3759a408b490a1eec05b8ae0",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "79608024-eeb4-4da4-ac39-be8260070222"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-13/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-13/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 445.469779041945,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-982d6923-48c3-4e2c-ab94-08337fecd2a0",
      "version": 1,
      "application_id": "app-ae9c4c62f5d1362f731e3873",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "5dad17bf-573c-4ab5-9afd-6af96546f45e"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-13/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-13/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 457.41294679197017,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-ece9b97b-8899-4d29-8228-d637525415bf",
      "version": 1,
      "application_id": "app-0ffd0c8a72d9b9db3da6ca9d",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "c6498f2d-055c-4fec-a7be-535d665787b4"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-13/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-13/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "46d04bdcbdbe4008a283adf6be0c018c"
            },
            {
              "request_id": "509af70ab1c84416add4821b949cfb2f"
            },
            {
              "request_id": "4495d9c9fbfa414ca4f1b7572c4a58df"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-13/c6498f2d-055c-4fec-a7be-535d665787b4/execution/capture/evidence/S000041_sample_000001/raw/0014-screenshot-plan.json",
              "sha256": "85198fa938a5d9f8d9730fcc7ead2a64cdb4d3f01087e36852e75e7b15b2a238"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-13/c6498f2d-055c-4fec-a7be-535d665787b4/execution/capture/evidence/S000041_sample_000001/raw/raw-receipt.json",
              "sha256": "f3ab447e3cf5132a310e977d772ccfda802ff2f0d5ef2ca38b418c96254ba0ff"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 539.9556953749852,
      "effective_steps": 0,
      "first_request_plan_accepted": false,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-13/runtime.jsonl",
        "line": 15
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 3,
        "states": {
          "succeeded": 3
        },
        "dispatch": {
          "dispatched": 3
        },
        "input_tokens": 31738,
        "output_tokens": 2688,
        "known_input_tokens": 31738,
        "known_output_tokens": 2688,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-a209ea59-e22f-40cd-bd8a-ba00b22e9db9",
      "version": 1,
      "application_id": "app-d64d6954ab4483412bfb3d4a",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "d215b09e-30a5-40c1-ad74-35fef0902814"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-13/runtime.jsonl",
              "line": 36
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-13/runtime.jsonl",
              "line": 38
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "cd8c83c7f5f349469c46289aee8201ea"
            },
            {
              "request_id": "63fc1355d66f48a8ac6afcef2b226948"
            },
            {
              "request_id": "aa3bc557735946a6aa2ec35fee5fecd3"
            },
            {
              "request_id": "5a3b7073c8b64a33ad8194b437a3170a"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "failed",
          "code": "ACCEPTANCE_SOURCE_INVALID",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-13/runtime.jsonl",
              "line": 46
            }
          ],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-13/d215b09e-30a5-40c1-ad74-35fef0902814/execution/capture/evidence/S000178_sample_000001/raw/raw-receipt.json",
              "sha256": "125d687889757dd95da9ed5249020ccd4a1fa8e4ea32d6102673f873c8dd1554"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 209.8836281299591,
      "session_elapsed_seconds": 206.91376370901708,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 4,
        "states": {
          "invalid_response": 2,
          "succeeded": 2
        },
        "dispatch": {
          "dispatched": 4
        },
        "input_tokens": 57615,
        "output_tokens": 3194,
        "known_input_tokens": 57615,
        "known_output_tokens": 3194,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c9a4af0b-c2d4-4134-b0b7-579798b6dc5b",
      "version": 1,
      "application_id": "app-bc9b5b27eb3c32f1774429d6",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "90972f16-623b-409f-b0d4-2a2d35e4a450"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-14/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-14/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 120.61786654195748,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-733e5c29-3536-46bc-80ba-cf201dc6811b",
      "version": 1,
      "application_id": "app-6cd7b65ba2ab7aa4639301be",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "77af9c2a-971a-4810-9374-2a6c7e8a72bb"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-14/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-14/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 414.0084671250079,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-f45aa53f-90ae-41c2-a756-820078cd2671",
      "version": 1,
      "application_id": "app-f8047ab6666258671666046f",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "413d838d-b0c7-470a-9a3c-e2a4c1228451"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-14/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-14/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 445.76368720899336,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-911ccf31-e8bf-46e9-a877-3be283ff0581",
      "version": 1,
      "application_id": "app-f26113b93443c5df3770b880",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "ae2252fe-fdc2-431c-9ac0-6295842eb513"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-14/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-14/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "445c091e65c14e6ca5ddc03b87d37337"
            },
            {
              "request_id": "0707aa66fefb4ff9be00b0cbb2876a68"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "failed",
          "code": "BUSINESS_ROLE_CONFLICT",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-14/runtime.jsonl",
              "line": 15
            }
          ],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-14/ae2252fe-fdc2-431c-9ac0-6295842eb513/execution/capture/evidence/S000169_sample_000003/raw/raw-receipt.json",
              "sha256": "b34392d38551c6d0290538ee0ba90da25a42a6bbf6f0df8dd6c5d6becdc36bbf"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 384.3362259864807,
      "session_elapsed_seconds": 373.47129024995957,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 2,
        "states": {
          "succeeded": 2
        },
        "dispatch": {
          "dispatched": 2
        },
        "input_tokens": 36283,
        "output_tokens": 2163,
        "known_input_tokens": 36283,
        "known_output_tokens": 2163,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-443c8926-6101-44a0-b0a0-b68c605f9f4d",
      "version": 1,
      "application_id": "app-470f2e6b8278a0fea9994c7e",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "4b64e716-2516-439f-bb9f-cd6af74eeae0"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-14/runtime.jsonl",
              "line": 27
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-14/runtime.jsonl",
              "line": 29
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "4e18a46cb3a340b092cc17f0fd9ad556"
            },
            {
              "request_id": "f4f9d0d2b8d742bb97cb775cc8ee056d"
            },
            {
              "request_id": "395ad930586b46d599601e02df9db13e"
            },
            {
              "request_id": "b5bce9513bc74713a9a8799e92b8e12e"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "failed",
          "code": "RATIONALE_NOT_GROUNDED",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-14/runtime.jsonl",
              "line": 37
            }
          ],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-14/4b64e716-2516-439f-bb9f-cd6af74eeae0/execution/capture/evidence/S000182_sample_000001/raw/raw-receipt.json",
              "sha256": "dd8d42082a82f55dbadfa6f65d19156fd5e17893e36c34d931de013103a5471b"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 202.61847972869873,
      "session_elapsed_seconds": 200.2449127919972,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 4,
        "states": {
          "invalid_response": 2,
          "succeeded": 2
        },
        "dispatch": {
          "dispatched": 4
        },
        "input_tokens": 45903,
        "output_tokens": 1835,
        "known_input_tokens": 45903,
        "known_output_tokens": 1835,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-9cb15540-3bc8-4d07-8bcc-054216b5f5d2",
      "version": 1,
      "application_id": "app-dbf591b0fd48fd4985d99609",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "f72c6ec8-f47d-4897-9291-a27ff217ca15"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-15/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-15/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 129.22083762509283,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-b9fb3c1f-47b2-4e26-aac9-a17c2b26fab0",
      "version": 1,
      "application_id": "app-0fa00ada4df12cd3081de310",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "EvidenceStale",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-15/fbb44604-1e02-466c-8736-d110bc1e6154/first-observation-failure.json",
              "sha256": "678c840aa8a521ef6bf8270e30249be639dd92112acff062ccc503ab987b3230"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 346.62695562501904,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-548ed845-f414-48ce-b396-a2ce8c043bc6",
      "version": 1,
      "application_id": "app-25078546eb12a715f8a3d1b8",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "eb16a784-37d1-49bb-b057-c8b007138cf5"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-15/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-15/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "2b087387287347e68d26fd5e08f1dd28"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-15/eb16a784-37d1-49bb-b057-c8b007138cf5/execution/capture/evidence/S000199_sample_000001/raw/raw-receipt.json",
              "sha256": "7f8f23ef3ffad968b0219c959feae6e440ff95a727c988dde2aef10706c6085f"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 409.52354097366333,
      "session_elapsed_seconds": 401.24334341695067,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 1,
        "states": {
          "invalid_response": 1
        },
        "dispatch": {
          "dispatched": 1
        },
        "input_tokens": 19106,
        "output_tokens": 1070,
        "known_input_tokens": 19106,
        "known_output_tokens": 1070,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-fd0e5779-2c97-4cf9-8774-cd106b04bc27",
      "version": 1,
      "application_id": "app-a4d8cbe098478296fb4691a7",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "cba11260-6b44-4d85-89fa-b1ee69a1a5a4"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "EvidenceStale",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-15/cba11260-6b44-4d85-89fa-b1ee69a1a5a4/first-observation-failure.json",
              "sha256": "0970aeb7894aaedb4cc214f3246edbda5d8b92977c43c58a5af45a323fe94074"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 27.459586143493652,
      "session_elapsed_seconds": 22.31911200005561,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-0c7dc0fa-6003-4e6f-b568-3f0771dd009e",
      "version": 1,
      "application_id": "app-40761e8342e1bf94df5c7338",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "b9bfbb17-9376-4666-8f32-ee42b41f59f9"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-15/runtime.jsonl",
              "line": 32
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-15/runtime.jsonl",
              "line": 34
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 30.815918250009418,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-60668b3c-97bf-43fb-996b-eb12e173887d",
      "version": 1,
      "application_id": "app-c4db227826711d6032e86727",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "5a7c68ef-a93f-4062-b743-0c6fb6c4decc"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-16/5a7c68ef-a93f-4062-b743-0c6fb6c4decc/first-observation-failure.json",
              "sha256": "a87ee26914c9750cf46ba776fb14b98fb7775b429d929b2f55a621faa096101e"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 133.16744709014893,
      "session_elapsed_seconds": 85.1361702500144,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-614e4867-8405-472e-be75-052251059878",
      "version": 1,
      "application_id": "app-d9bee133eb462ac25592ffcb",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "920721b7-25b7-4f95-a29d-6edef302b7e4"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-16/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-16/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 443.3871402500663,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-0bdd2528-8579-42f5-8ebc-2006e0ba2bc3",
      "version": 1,
      "application_id": "app-d9b9d3397a42bc56d35cd0ef",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "e02de86e-c7b2-4b70-afe9-4650445254c6"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-16/e02de86e-c7b2-4b70-afe9-4650445254c6/first-observation-failure.json",
              "sha256": "f28650039332afab3f0ac4657dcbb4326d8eb2e29d380ca7d8a7d29bb9864c6b"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 45.993969202041626,
      "session_elapsed_seconds": 33.71026341698598,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d4e895fe-fd3c-4d60-9c1a-7d5add220050",
      "version": 1,
      "application_id": "app-142addf092d49dad155909bf",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "905dfc40-4011-45e5-8e88-b23f4d388735"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-16/runtime.jsonl",
              "line": 14
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-16/runtime.jsonl",
              "line": 16
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 421.816628917004,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-0152558e-3d8d-433e-8813-957d6ab51558",
      "version": 1,
      "application_id": "app-31d149f04de3de94390a11ce",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "757736b6-0a41-475d-9b6d-2fc9e8326500"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-16/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-16/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "eb4fcc807f574b6292a8b53f1a40d54f"
            },
            {
              "request_id": "ff61d5cf5e9c422bac53bec323d2b50a"
            },
            {
              "request_id": "59f98bca784d431eae1d6cd7db2d8cab"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "failed",
          "code": "ACCEPTANCE_SOURCE_INVALID",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-16/runtime.jsonl",
              "line": 13
            }
          ],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-16/757736b6-0a41-475d-9b6d-2fc9e8326500/execution/capture/evidence/S000250_sample_000001/raw/raw-receipt.json",
              "sha256": "3367490de755fd22d36c93b40db6cc7db6476934aa68fb3e5c2ef030043ce5ed"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 244.05673789978027,
      "session_elapsed_seconds": 235.49537658307236,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 3,
        "states": {
          "succeeded": 1,
          "invalid_response": 2
        },
        "dispatch": {
          "dispatched": 3
        },
        "input_tokens": 50956,
        "output_tokens": 2756,
        "known_input_tokens": 50956,
        "known_output_tokens": 2756,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-755e6d12-178b-40ba-8eb2-07180fe8417c",
      "version": 1,
      "application_id": "app-7bb632acb232d88045e1b659",
      "template": "long_reading",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "e44cd977-9d70-4813-9b7b-20493adc60df"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-17/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-17/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 132.7954962910153,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d9f815d5-edbc-4420-aefc-17aebb00ca8d",
      "version": 1,
      "application_id": "app-2256b505c259ec4365c64594",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "e66f8390-d5cc-4660-9492-e904079e5efe"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-17/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-17/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 431.523907625,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-43a1498b-45f4-4164-90e6-4becc87fb4c2",
      "version": 1,
      "application_id": "app-98bb795629ae9e7d8271f984",
      "template": "operation",
      "template_source": "site_rule",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "58a0c976-c88f-45df-9e23-b8d4280cb2f1"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-17/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-17/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "8d358b5768f44060a83a7adbf5a3a756"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-17/58a0c976-c88f-45df-9e23-b8d4280cb2f1/execution/capture/evidence/S000001_sample_000197/raw/0009-screenshot-plan.json",
              "sha256": "e6c1a6c531a71901f4834bf4147c6670cc545e830b4b62805a1a986cce8872b6"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-17/58a0c976-c88f-45df-9e23-b8d4280cb2f1/execution/capture/evidence/S000001_sample_000197/raw/raw-receipt.json",
              "sha256": "7c15289b53286d05fa3e3628b00a3447f07c2cba3327ba73348491662f330082"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 258.0628228187561,
      "session_elapsed_seconds": 251.96668783400673,
      "effective_steps": 1,
      "first_request_plan_accepted": true,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-17/runtime.jsonl",
        "line": 13
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 1,
        "states": {
          "succeeded": 1
        },
        "dispatch": {
          "dispatched": 1
        },
        "input_tokens": 11153,
        "output_tokens": 995,
        "known_input_tokens": 11153,
        "known_output_tokens": 995,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-fa07d8e3-1863-4d61-b320-4c9cbb9c388c",
      "version": 1,
      "application_id": "app-692a94fed923f056a6a862fd",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "81d38088-19d1-4177-8785-3731f6da4a15"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-17/81d38088-19d1-4177-8785-3731f6da4a15/first-observation-failure.json",
              "sha256": "7e5ddbdba11d13f0abc3d96ad20300fd9da176e437a4c29062971d5a00f2d23d"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 9.847620964050293,
      "session_elapsed_seconds": 4.269520750036463,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-1fa4dd1c-193b-434a-a146-0f79f8723594",
      "version": 1,
      "application_id": "app-e3de3e48b34ab6788b7fd88c",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "d6e5d7f8-36a1-458d-9a23-ee55da31d8d0"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-17/d6e5d7f8-36a1-458d-9a23-ee55da31d8d0/first-observation-failure.json",
              "sha256": "62755faee3e4f26ebe65ed77f796b4a91fd30d738bce9ebb6f62ec08355771e6"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 15.008938074111938,
      "session_elapsed_seconds": 8.410796875017695,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-3d0cb7be-5140-4514-930f-a3b196406300",
      "version": 1,
      "application_id": "app-69ff7af2ff194f3bd06fd4f7",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "cbf160f6-57bf-4350-af15-8a9799283983"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-18/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-18/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 138.14666287507862,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-6988387d-88f5-487c-826d-b569b8f533fb",
      "version": 1,
      "application_id": "app-9edd3238c39e0ec4f8ba2a4d",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "d388e77b-6eb9-4266-b729-459a308c8118"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-18/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-18/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 435.35918958403636,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c5693ffd-64bb-4ec8-b695-0068448678e0",
      "version": 1,
      "application_id": "app-7997578ee50cd7f69091be58",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "baabcc08-6efd-4d93-a87b-3c0ced4106a7"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-18/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-18/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 466.1867342919577,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d9a660fc-f040-48e1-b95a-969ae6300f51",
      "version": 1,
      "application_id": "app-a14a91aa44851afdd6775189",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "cd307708-4723-445b-81d4-3a37e4aa0c3e"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-18/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-18/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "ad3cbe838e6d4f2aa18985bde6dc6a39"
            },
            {
              "request_id": "2f4ea75d41f64f10803bb29988780e30"
            },
            {
              "request_id": "b837a87e9ddc4099b8ec8e6341cee778"
            },
            {
              "request_id": "d68d5657804043bf8a7501a289d52eb6"
            },
            {
              "request_id": "d3c7b6f355e740e28dbe795445ac7cf9"
            },
            {
              "request_id": "49924b4392d041f2ad1a11550f01ad1c"
            },
            {
              "request_id": "517dade9f8434e8a95eb6446cf603e65"
            },
            {
              "request_id": "58f4529cbac64548bcd2c4ccd48a13d1"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-18/cd307708-4723-445b-81d4-3a37e4aa0c3e/execution/capture/evidence/S000027_sample_000001/raw/0009-screenshot-plan.json",
              "sha256": "ed25e83e3469548a462ca5dcc2fb4271de8c51fc9fffa4b3d1b3199bb1f8569f"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-18/cd307708-4723-445b-81d4-3a37e4aa0c3e/execution/capture/evidence/S000027_sample_000001/raw/raw-receipt.json",
              "sha256": "67c8df5cf65cfd8c72771c1e6bffcd6fb0c85069f29beaf34ff42601a8b47836"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 522.4507977962494,
      "session_elapsed_seconds": 515.2351144170389,
      "effective_steps": 3,
      "first_request_plan_accepted": true,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-18/runtime.jsonl",
        "line": 13
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 8,
        "states": {
          "succeeded": 7,
          "invalid_response": 1
        },
        "dispatch": {
          "dispatched": 8
        },
        "input_tokens": 134499,
        "output_tokens": 3829,
        "known_input_tokens": 134499,
        "known_output_tokens": 3829,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-ae6d2bba-aad5-48e2-a65a-81e3fd9692bf",
      "version": 1,
      "application_id": "app-d533e3a4791e825199bf2c30",
      "template": "long_reading",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "7a6c8411-d162-499f-b7b1-f6ffc2843340"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-18/runtime.jsonl",
              "line": 61
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-18/runtime.jsonl",
              "line": 63
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "9c096118731f40d3b95f5562bb498c7e"
            },
            {
              "request_id": "fb7a69a3a5464edfb48d09679aad9024"
            },
            {
              "request_id": "d0578019e7494be9a57f1b40e99eba02"
            },
            {
              "request_id": "b2481e457d1a43a882a963e71a2706df"
            },
            {
              "request_id": "69c46f45a7e24ab69bda9addafd95046"
            },
            {
              "request_id": "c0888bc5d06c4bedb6b9150074a1ed3d"
            },
            {
              "request_id": "0d0867e98280428b90db61ea19fba0c8"
            },
            {
              "request_id": "6e334c0cd97d4fd790d74eb7cc5fe364"
            },
            {
              "request_id": "bd99f43895dc43c9ade45c7528b52248"
            },
            {
              "request_id": "571f02a713014668a0c1027328373061"
            },
            {
              "request_id": "a9beac12482745738b09ecc0b5c8404d"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-18/7a6c8411-d162-499f-b7b1-f6ffc2843340/execution/capture/evidence/S000113_sample_000001/raw/0010-screenshot-plan.json",
              "sha256": "9d170d3f10a258f0d2d4f9e1a5a159a59e0a494c4c67af385ab02a838b24a648"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "reached",
          "code": null,
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-18/7a6c8411-d162-499f-b7b1-f6ffc2843340/execution/capture/evidence/S000113_sample_000001/raw/raw-receipt.json",
              "sha256": "51ea9babeb1254bb259370111b09fd72997bd5812bc079b37112a664515766d2"
            }
          ],
          "prefix_reached": true
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 526.5774641036987,
      "session_elapsed_seconds": 524.3821156249614,
      "effective_steps": 11,
      "first_request_plan_accepted": false,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-18/runtime.jsonl",
        "line": 69
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 11,
        "states": {
          "invalid_response": 1,
          "succeeded": 10
        },
        "dispatch": {
          "dispatched": 11
        },
        "input_tokens": 219788,
        "output_tokens": 6919,
        "known_input_tokens": 219788,
        "known_output_tokens": 6919,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-56eb5eb2-e8bd-4601-a30f-c0077c21c4e8",
      "version": 1,
      "application_id": "app-2534307b2632cec2f235901d",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "dc51bbd6-7803-4034-aa1c-d99c05a1790d"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-19/dc51bbd6-7803-4034-aa1c-d99c05a1790d/first-observation-failure.json",
              "sha256": "fee6e0f09c0c2aeb154f222951b2b503210a9dd338b722876ad4e5c16f027518"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 116.05812883377075,
      "session_elapsed_seconds": 59.257773499935865,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-f7389a74-7be3-4c27-8fcb-ee07aa7eb2c6",
      "version": 1,
      "application_id": "app-7fbe8bdae7a8b2ade139044b",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "5b2aa771-efea-485a-af15-58776aaf4a45"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "EvidenceStale",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-19/5b2aa771-efea-485a-af15-58776aaf4a45/first-observation-failure.json",
              "sha256": "9ee4a76a33ce7ecbb63caa8fa6d344613bfdd1b3cf619bcd2f78586f40fa31ad"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 296.6131100654602,
      "session_elapsed_seconds": 222.7153674159199,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-28eecdec-64b4-4ba5-8b78-537347741125",
      "version": 1,
      "application_id": "app-636a2f32f6f61b737150de21",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "3909246f-658d-486b-acd3-452c33b533eb"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-19/runtime.jsonl",
              "line": 14
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 76.74005337501876,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-8b1b8428-f500-4dea-979f-c800d83e7f0e",
      "version": 1,
      "application_id": "app-95f7633955f9037494bbe989",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "0399f563-2595-44ec-928d-177f41d17649"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-19/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-19/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "ad00cc99493a49eaab8a2e518099ebfa"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-19/0399f563-2595-44ec-928d-177f41d17649/execution/capture/evidence/S000048_sample_000001/raw/0009-screenshot-plan.json",
              "sha256": "3b9d23f4dc58b84c08942b7e65264d91c445edd124dbef9b7dd89ec049873602"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118091153-ad5d732d/fixed-20261118091153-ad5d732d-19/0399f563-2595-44ec-928d-177f41d17649/execution/capture/evidence/S000048_sample_000001/raw/raw-receipt.json",
              "sha256": "f76c81f3ff9ab33961c741d94ab26aabbcde3280cbdbaecff335e1f27524fe09"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 461.73933550005313,
      "effective_steps": 0,
      "first_request_plan_accepted": true,
      "closure_proven": false,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-19/runtime.jsonl",
        "line": 13
      },
      "task_terminal_proven": false,
      "requests": {
        "requests": 1,
        "states": {
          "succeeded": 1
        },
        "dispatch": {
          "dispatched": 1
        },
        "input_tokens": 12747,
        "output_tokens": 969,
        "known_input_tokens": 12747,
        "known_output_tokens": 969,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-2756e068-26c4-44bf-a3e5-ef7eb4e63f97",
      "version": 1,
      "application_id": "app-57e27368f9fb3d90ed521bf0",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "8459eef1-ce4b-400c-8235-c9ce6e9bbe5b"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-19/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-19/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "c2bd55a6f2334f96b53b635f493a66ec"
            },
            {
              "request_id": "18af150615414aa2bcec59643e09e724"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-19/8459eef1-ce4b-400c-8235-c9ce6e9bbe5b/execution/capture/evidence/S000164_sample_000005/raw/0009-screenshot-plan.json",
              "sha256": "7e5fbad97b6cd6c575d2904af5c6d5e140fd0c39cf7a245c79510e9ed07ef0bb"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-19/8459eef1-ce4b-400c-8235-c9ce6e9bbe5b/execution/capture/evidence/S000164_sample_000005/raw/raw-receipt.json",
              "sha256": "5fc4c283408d6f50e7003a0050ba1d94d5d3e73c972a27045a361ac997317946"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 569.0033815420466,
      "effective_steps": 2,
      "first_request_plan_accepted": true,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-19/runtime.jsonl",
        "line": 13
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 2,
        "states": {
          "succeeded": 2
        },
        "dispatch": {
          "dispatched": 2
        },
        "input_tokens": 30560,
        "output_tokens": 1519,
        "known_input_tokens": 30560,
        "known_output_tokens": 1519,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-e6125765-b9df-4499-a4bd-40acd3ec1b70",
      "version": 1,
      "application_id": "app-f5189cfa26c0bbd0f14c08b1",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "e32faa2e-915a-4c42-b61f-0e5007ef86ae"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-20/e32faa2e-915a-4c42-b61f-0e5007ef86ae/first-observation-failure.json",
              "sha256": "c124eb277d0e13ddf327220a05fd218d4e1f5756f4493d89dec4267ec85a22c0"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 129.68850898742676,
      "session_elapsed_seconds": 75.84302899998147,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-18afbdac-19bb-4233-b430-5b3e6b2c73d9",
      "version": 1,
      "application_id": "app-e79976782188a884e4e6d6fe",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "2e834a38-66d2-454f-82c6-5776001bdb52"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-20/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-20/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 440.6283785420237,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-507d59f7-6ae6-41aa-95e4-131f1ad610e9",
      "version": 1,
      "application_id": "app-fc64872577d7c22f2d8b2bd0",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "532fae48-cdb4-43af-96f8-62e895ac28c7"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-20/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-04/runtime/fixed-20261118091153-ad5d732d-20/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 455.2430781250587,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-133749d6-1200-400b-879b-9988f4dd69cb",
      "version": 1,
      "application_id": "app-758780c85e102a55d26755b7",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "2aa5301e-54a9-4aed-9f2a-771a50431abb"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-20/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-20/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "9465b2c8a8db473193d502b7b6b01d36"
            },
            {
              "request_id": "91a99e57242f46dd98c633f05637e843"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-20/2aa5301e-54a9-4aed-9f2a-771a50431abb/execution/capture/evidence/S000162_sample_000003/raw/0009-screenshot-plan.json",
              "sha256": "c9f7a78093f7602fc6e142a3e1cb3108fdeff7907e610d45aa184524d8942987"
            }
          ],
          "prefix_reached": true
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-20/2aa5301e-54a9-4aed-9f2a-771a50431abb/execution/capture/evidence/S000162_sample_000003/raw/raw-receipt.json",
              "sha256": "c5ed499df2d77e8aa530ce64f3050166d72f34c2eea8e0e24c925f89f539a8f8"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 483.5976838750066,
      "effective_steps": 2,
      "first_request_plan_accepted": false,
      "closure_proven": true,
      "plan_accept_log": {
        "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-20/runtime.jsonl",
        "line": 13
      },
      "task_terminal_proven": true,
      "requests": {
        "requests": 2,
        "states": {
          "invalid_response": 1,
          "succeeded": 1
        },
        "dispatch": {
          "dispatched": 2
        },
        "input_tokens": 27618,
        "output_tokens": 1168,
        "known_input_tokens": 27618,
        "known_output_tokens": 1168,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-8796ff60-67b6-4378-9b9a-7f017ea699ca",
      "version": 1,
      "application_id": "app-72e259702360691d76096239",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "d4484e61-c9e8-4bcb-8204-afdbb8286e9f"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-20/runtime.jsonl",
              "line": 43
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-20/runtime.jsonl",
              "line": 45
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "reached",
          "evidence": [
            {
              "request_id": "0cd807732c56449384756ad3045b83bd"
            },
            {
              "request_id": "c08c3d257f204210befc6221513c8431"
            },
            {
              "request_id": "9c6ce80e19d642aa9fe5b12769ea196f"
            }
          ],
          "prefix_reached": true
        },
        "initial_plan_accepted": {
          "state": "failed",
          "code": "EVIDENCE_ROUTE_INVALID",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-05/runtime/fixed-20261118092858-d2c055c7-20/runtime.jsonl",
              "line": 53
            }
          ],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "failed",
          "code": "effective_steps_below_5",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118092858-d2c055c7/fixed-20261118092858-d2c055c7-20/d4484e61-c9e8-4bcb-8204-afdbb8286e9f/execution/capture/evidence/S000028_sample_000001/raw/raw-receipt.json",
              "sha256": "62e10b55df6a57a558e026754de2f2eb374a5db2d9d8b02647d77565f0e21375"
            }
          ],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 266.82660603523254,
      "session_elapsed_seconds": 262.492119917064,
      "effective_steps": 0,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 3,
        "states": {
          "invalid_response": 1,
          "succeeded": 2
        },
        "dispatch": {
          "dispatched": 3
        },
        "input_tokens": 32055,
        "output_tokens": 2861,
        "known_input_tokens": 32055,
        "known_output_tokens": 2861,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    }
  ],
  "qc": "NOT_RUN",
  "human_review": "NOT_RUN",
  "published": false,
  "acceptance": "UNKNOWN"
}
```
