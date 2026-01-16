# Statistical Rethinking: A Comprehensive Methodology Guide
## Based on Richard McElreath's "Statistical Rethinking"

This document summarizes the key Bayesian modeling methodologies from Statistical Rethinking, focusing on the conceptual foundations, when to apply each method, and the importance of DAGs and causal reasoning throughout.

---

# Table of Contents

1. [Causal Inference Pitfalls (Chapter 6)](#causal-inference-pitfalls)
2. [Conditioning Explained](#conditioning-explained)
3. [Entropy and Accuracy (Chapter 7)](#entropy-and-accuracy)
4. [Interactions (Chapter 8)](#interactions)
5. [Generalized Linear Models (Chapter 10)](#generalized-linear-models)
6. [Count Data Models (Chapter 11)](#count-data-models)
7. [Monsters and Mixtures (Chapter 12)](#monsters-and-mixtures)
8. [Multilevel Models (Chapter 13)](#multilevel-models)
9. [Covariance and Gaussian Processes (Chapter 14)](#covariance-and-gaussian-processes)
10. [Missing Data (Chapter 15)](#missing-data)
11. [Custom Likelihoods (Chapter 16)](#custom-likelihoods)
12. [Model Comparison and Criticism (Chapter 17)](#model-comparison-and-criticism)

---

# Causal Inference Pitfalls

These three concepts are covered primarily in **Chapter 6** ("The Haunted DAG & The Causal Terror"). They all relate to the central question: *which variables should we include in our model?*

## 1. Multicollinearity

### What It Is
Multicollinearity occurs when two or more predictor variables are strongly correlated with each other. When this happens, the model can predict the outcome well, but it cannot distinguish *which* predictor is responsible for the effect. The posterior distributions for individual coefficients become very wide and uncertain, even though the model's overall predictive power remains strong.

### The DAG Perspective
Multicollinearity is primarily an **estimation problem**, not necessarily a causal one. Consider McElreath's classic leg-length example:

```
Height ← Left_Leg
Height ← Right_Leg
Left_Leg ↔ Right_Leg (strongly correlated)
```

Both legs carry nearly identical information about height. When you include both, the model essentially asks: "How much does left leg length predict height, *holding right leg constant*?" This question is nearly meaningless because legs don't vary independently.

### When Your Data Needs This Consideration
- **Symptom**: Wide posterior intervals on coefficients that individually should matter, but the model predicts well overall
- **Diagnostic**: Check pairwise correlations among predictors; examine the posterior correlation between coefficient estimates (they'll be highly negative when multicollinear)
- **Common scenarios**: Including multiple indicators of the same underlying construct (e.g., multiple socioeconomic variables, multiple body measurements)

### The Solution Approach
- If you need causal inference on a specific variable, consider which predictors truly represent distinct causal paths
- Sometimes multicollinearity reveals that you're asking a question your data cannot answer
- The posterior *distribution* tells you honestly about this uncertainty—the model isn't broken, it's correctly reporting ambiguity

---

## 2. Post-Treatment Bias

### What It Is
Post-treatment bias occurs when you include a variable in your model that is **causally downstream** of the treatment/exposure you're studying. By conditioning on this post-treatment variable, you block part of the causal pathway and potentially distort your estimate of the treatment effect.

### The DAG Perspective
Consider McElreath's plant growth example:

```
Treatment → Fungus → Growth
Treatment → Growth (direct effect)
```

If treatment reduces fungus, and fungus reduces growth, then:
- The **total effect** of treatment includes both the direct path and the indirect path through fungus
- If you condition on fungus (include it as a predictor), you block the indirect path
- You now estimate only the direct effect, not the total causal effect

Worse still, if there are unmeasured confounders between the post-treatment variable and the outcome, conditioning on the post-treatment variable can introduce bias even in estimating the direct effect.

### When Your Data Needs This Consideration
- **Question to ask**: "Could this predictor be *caused by* my treatment variable?"
- **Common scenarios**:
  - Medical studies: controlling for symptoms that develop after treatment begins
  - Education research: controlling for intermediate test scores when studying a teaching method's effect on final performance
  - Business: controlling for customer behavior metrics that occur after a marketing intervention

### The Solution Approach
- Draw your DAG before modeling—identify the temporal and causal ordering of variables
- Be explicit about whether you want the **total effect** or the **direct effect** (they require different adjustment sets)
- Variables measured *before* treatment are generally safe; variables measured *after* treatment require careful DAG analysis

---

## 3. Collider Bias (Selection-Distortion Effect)

### What It Is
A **collider** is a variable that is caused by two or more other variables—arrows point *into* it on the DAG. When you condition on a collider, you create a **spurious statistical association** between its causes, even if those causes are truly independent.

This is perhaps the most counterintuitive of the three: including a variable can *create* confounding where none existed.

### The DAG Perspective
Classic structure:

```
Trustworthiness → Selection
Newsworthiness → Selection
```

Trustworthiness and newsworthiness of research proposals might be independent in the population. But if a funding agency selects proposals that are *either* highly trustworthy *or* highly newsworthy (selection is the collider), then among funded proposals, you'll observe a negative correlation: trustworthy proposals will tend to be less newsworthy, and vice versa. This correlation is entirely an artifact of conditioning on selection.

McElreath's marriage/age/happiness example:
```
Age → Marriage
Happiness → Marriage
```

If you want to study whether age affects happiness, and you condition on marital status, you've opened a backdoor path through the collider, creating spurious associations.

### When Your Data Needs This Consideration
- **Question to ask**: "Is this variable I'm conditioning on *caused by* both my predictor of interest and my outcome (or another predictor)?"
- **Common scenarios**:
  - Selection effects: studying only published papers, successful companies, hospitalized patients
  - Survivorship bias: studying characteristics of things that "made it"
  - Stratifying by a common effect of your variables of interest
  
### The Solution Approach
- On a DAG, conditioning on a collider **opens** a path rather than closing one
- If you must condition on a collider (e.g., your data inherently comes from a selected population), recognize that your inferences may not generalize
- Sometimes you can use sensitivity analysis to bound the potential bias

---

## Summary Table: Causal Inference Pitfalls

| Bias Type | DAG Structure | Problem | What Happens |
|-----------|---------------|---------|--------------|
| **Multicollinearity** | X₁ ↔ X₂ → Y | Predictors too similar | Wide posteriors, can't distinguish effects |
| **Post-treatment** | X → Z → Y | Condition on mediator | Blocks causal pathway, biases total effect |
| **Collider** | X → Z ← Y | Condition on common effect | Opens spurious path, creates false association |

## The Core Lesson

McElreath emphasizes that there is no universal rule like "include all variables" or "include only significant variables." The decision of what to include must be guided by your **causal model** (DAG). The same variable might be:
- Essential to include (to close a backdoor path)
- Harmful to include (if it's a collider or post-treatment)
- Irrelevant (if it's not on any path between your variables of interest)

---

# Conditioning Explained

**Conditioning** means restricting your analysis or inference to specific values or subsets of a variable. It's essentially asking: "Given that we know X, what can we say about Y?"

## Three Ways Conditioning Happens

### 1. Including a Variable in Your Model
When you add a predictor to a regression, you're conditioning on it. The model estimates the relationship between other variables **while holding that predictor constant**.

```
# Not conditioning on Z
Y ~ X

# Conditioning on Z
Y ~ X + Z
```

The second model asks: "What is the effect of X on Y, *for observations with the same value of Z*?"

### 2. Stratifying or Subsetting Data
If you analyze only married people, or only patients who survived, you're conditioning on that variable.

### 3. Selection Into Your Dataset
If your data only contains certain observations (published studies, successful startups, hospitalized patients), you're implicitly conditioning on whatever process selected them.

## Why It Matters for DAGs

Conditioning has opposite effects depending on the DAG structure:

| Structure | Conditioning Effect |
|-----------|-------------------|
| **Confounder**: X ← Z → Y | **Closes** the backdoor path (good) |
| **Mediator**: X → Z → Y | **Blocks** the causal pathway (may be bad) |
| **Collider**: X → Z ← Y | **Opens** a spurious path (bad) |

The same mechanical operation—adding Z to your model—can help, hurt, or distort your causal inference depending entirely on Z's position in the causal structure.

## Simple Intuition

Think of conditioning as **filtering your view**. When you condition on Z:
- You're only comparing observations that share the same Z value
- Any variation in Z is removed from consideration
- This can reveal relationships, hide them, or create phantom ones—depending on the causal structure

---

# Entropy and Accuracy

Chapter 7 ("Ulysses' Compass") addresses **model comparison**—how do we choose between models of different complexity? Entropy provides the theoretical foundation.

## What Is Entropy?

Entropy is a measure of **uncertainty** or **information** in a probability distribution. It answers the question: *How surprised should we expect to be?*

### The Core Intuition

Imagine predicting weather in two cities:

**City A**: Rain 50% of days, sun 50% of days
**City B**: Rain 99% of days, sun 1% of days

Which city is easier to predict? City B—you just guess rain every day and you're almost always right. City A keeps you guessing.

**Entropy quantifies this.** High entropy means high uncertainty (City A). Low entropy means the distribution is concentrated and predictable (City B).

### The Formula

For a distribution with probabilities p₁, p₂, ..., pₙ:

$$H(p) = -\sum_{i} p_i \log(p_i)$$

Each term pᵢ log(pᵢ) measures how much "surprise" that outcome contributes, weighted by how often it occurs. Rare events are surprising but don't happen often; common events happen often but aren't surprising. Entropy balances these.

**Key properties:**
- Entropy is maximized when all outcomes are equally likely (maximum uncertainty)
- Entropy is zero when one outcome has probability 1 (no uncertainty)
- Adding more possible outcomes increases maximum possible entropy

## Why Entropy Matters in Chapter 7

### The Problem McElreath Sets Up

- Complex models fit training data better (lower in-sample error)
- But they **overfit**—they learn noise, not signal
- Simple models underfit—they miss real patterns
- We need a principled way to measure **out-of-sample predictive accuracy**

### Entropy Connects to Accuracy Through Divergence

**Kullback-Leibler (KL) Divergence** measures how much information is lost when we use our model Q to approximate the true distribution P:

$$D_{KL}(P || Q) = \sum_i p_i \log\frac{p_i}{q_i}$$

This can be rewritten as:

$$D_{KL}(P || Q) = H(P, Q) - H(P)$$

Where H(P, Q) is **cross-entropy**—the entropy of P measured using Q's probabilities.

**The insight:** Since H(P) is fixed (it's the true distribution's entropy), minimizing KL divergence is equivalent to minimizing cross-entropy. This gives us a target for model comparison.

## From Entropy to Predictive Accuracy

### Log-Pointwise-Predictive-Density (lppd)

McElreath introduces lppd as the Bayesian measure of predictive accuracy:

$$\text{lppd} = \sum_i \log \left( \frac{1}{S} \sum_s p(y_i | \theta_s) \right)$$

This is essentially the log-probability of observing your data, averaged across posterior samples. Higher lppd means better predictions.

**Connection to entropy:** lppd is directly related to cross-entropy. A model with higher lppd has lower cross-entropy with the true data-generating process.

### The Overfitting Problem

Training lppd is **always optimistic**—it overestimates how well the model will predict new data. The gap between training and out-of-sample performance grows with model complexity.

## Information Criteria as Entropy-Based Tools

### AIC (Akaike Information Criterion)

$$\text{AIC} = -2 \cdot \text{lppd} + 2k$$

Penalizes by number of parameters k. Assumes flat priors and large samples.

### WAIC (Widely Applicable Information Criterion)

$$\text{WAIC} = -2 \cdot \text{lppd} + 2 \cdot p_{WAIC}$$

The penalty term p_WAIC is computed from the posterior itself—it measures the **effective number of parameters** by looking at how much each observation's prediction varies across posterior samples.

**Why this works:** Observations where the posterior is uncertain (high variance in predictions) contribute more to overfitting. WAIC measures this directly rather than just counting parameters.

### PSIS-LOO (Pareto-Smoothed Importance Sampling Leave-One-Out)

Approximates leave-one-out cross-validation using importance sampling. More robust than WAIC when some observations are influential.

## The Deep Insight

Entropy tells us that:

1. **There's a fundamental tradeoff** between fitting known data and predicting new data

2. **Uncertainty has structure** that we can measure and use

3. **Model comparison should target prediction**, not fit—and entropy-based measures (lppd, WAIC, PSIS-LOO) give us principled ways to estimate predictive accuracy without actually collecting new data

4. **Regularization makes sense** because it trades worse in-sample fit for better expected out-of-sample performance (regularizing priors reduce effective parameters)

## Summary: Entropy Concepts

| Concept | What It Measures |
|---------|-----------------|
| **Entropy H(P)** | Uncertainty in a distribution |
| **Cross-entropy H(P,Q)** | Uncertainty in P using Q's probabilities |
| **KL Divergence** | Information lost using Q instead of P |
| **lppd** | Bayesian predictive accuracy (in-sample) |
| **WAIC/PSIS-LOO** | Estimated out-of-sample predictive accuracy |

---

# Interactions

Chapter 8 ("Conditional Manatees") addresses **interactions**—when the effect of one predictor depends on the value of another predictor.

## The Core Problem

Simple linear models assume predictors have **additive, independent effects**:

$$Y = \alpha + \beta_1 X_1 + \beta_2 X_2$$

Here, the effect of X₁ is always β₁, regardless of X₂'s value. But reality often works differently:

- The effect of water on plant growth depends on sunlight
- The effect of education on income depends on field of study
- The effect of a drug depends on patient age

**Interactions allow the effect of one variable to change based on another.**

## Building Interactions Into Models

### Continuous × Categorical Interaction

The simpler case. McElreath uses the example of ruggedness and GDP across African vs non-African nations.

**Without interaction:**
$$\mu_i = \alpha + \beta_R R_i + \beta_A A_i$$

Ruggedness (R) has the same effect everywhere. Being in Africa (A) shifts the intercept.

**With interaction:**
$$\mu_i = \alpha + \beta_R R_i + \beta_A A_i + \beta_{RA} R_i A_i$$

Now the effect of ruggedness is:
- In non-African countries (A=0): β_R
- In African countries (A=1): β_R + β_RA

The data reveals that rugged terrain is associated with *lower* GDP outside Africa but *higher* GDP within Africa (possibly because ruggedness protected against slave trade routes). Without the interaction, this pattern is invisible.

### Continuous × Continuous Interaction

More complex. Every combination of predictor values implies a different slope.

$$\mu_i = \alpha + \beta_1 X_1 + \beta_2 X_2 + \beta_{12} X_1 X_2$$

The effect of X₁ becomes:
$$\frac{\partial \mu}{\partial X_1} = \beta_1 + \beta_{12} X_2$$

This is now a **function of X₂**, not a single number.

## Interpreting Interactions

### The Symmetry of Interactions

A crucial insight: interactions are **symmetric**. If the effect of X₁ depends on X₂, then equally the effect of X₂ depends on X₁. The model doesn't privilege one interpretation.

$$\beta_{12} X_1 X_2$$

You can read this as:
- "The effect of X₁ changes by β₁₂ for each unit of X₂"
- "The effect of X₂ changes by β₁₂ for each unit of X₁"

Both are mathematically identical.

### Tables of Coefficients Are Not Enough

McElreath emphasizes that interaction coefficients are **difficult to interpret directly**. A table showing:

| Parameter | Estimate |
|-----------|----------|
| α | 1.2 |
| β₁ | 0.3 |
| β₂ | -0.5 |
| β₁₂ | 0.8 |

...tells you very little intuitively. What does β₁ = 0.3 mean when the actual effect of X₁ is β₁ + β₁₂X₂?

### Plotting Is Essential

The solution: **visualize predictions across the range of both variables**.

McElreath recommends:
1. **Triptych plots**: Show the predicted relationship at low, medium, and high values of the moderating variable
2. **Contour/surface plots**: For continuous × continuous interactions, show the full prediction surface
3. **Always include uncertainty**: Plot posterior intervals, not just means

## The DAG Perspective

Interactions don't change the DAG structure—they change the **functional form** within a causal path. If your DAG says:

```
X₁ → Y
X₂ → Y
```

An interaction means the causal effect of X₁ on Y is moderated by X₂. The arrows remain the same; the mathematical relationship along those arrows becomes more complex.

**Key point:** Interactions are about *how* causes combine, not *whether* they're causes.

## When Your Data Needs Interactions

### Signs You Should Consider Interactions

- **Theory suggests moderation**: Domain knowledge indicates one factor changes another's effect
- **Subgroup differences**: The relationship looks different when you split by a categorical variable
- **Nonlinear patterns**: A simple additive model shows systematic residual patterns
- **Different slopes in plots**: Visualizing Y vs X₁, colored by X₂, shows non-parallel lines

### Common Scenarios

| Domain | Interaction Example |
|--------|-------------------|
| Medicine | Drug effect × patient age |
| Agriculture | Water × sunlight on growth |
| Economics | Education × industry on wages |
| Psychology | Therapy × severity on outcomes |
| Ecology | Temperature × humidity on species |

## Practical Modeling Advice from McElreath

### Center Your Variables

When including interactions, **centering** predictors (subtracting the mean) helps interpretation:

- The "main effect" β₁ becomes the effect of X₁ *when X₂ is at its mean*
- Reduces correlation between main effects and interaction terms
- Makes coefficients more interpretable

### Be Skeptical of Interactions

Interactions require more data to estimate reliably than main effects. With limited data:
- Interaction estimates are noisy
- Regularizing priors help prevent overfitting
- Consider whether the interaction is scientifically plausible before including it

### Prediction vs Interpretation

- For **prediction**: Include interactions if they improve out-of-sample accuracy (check WAIC/PSIS-LOO)
- For **causal interpretation**: Only include interactions if your causal model justifies them

## Summary: Interactions

| Concept | Key Point |
|---------|-----------|
| **Interaction** | Effect of one predictor depends on another |
| **Symmetry** | X₁×X₂ interaction is interpretable both ways |
| **Coefficient tables** | Misleading for interactions—must visualize |
| **Centering** | Makes main effects interpretable at mean values |
| **DAG relationship** | Interactions are functional form, not structure |
| **When to use** | Theory-driven, check with WAIC, visualize always |

---

# Generalized Linear Models

Chapter 10 ("Big Entropy and the Generalized Linear Model") answers a fundamental question: **Why do we use the statistical distributions we use?** McElreath shows that maximum entropy provides a principled basis for choosing likelihood functions, leading to Generalized Linear Models (GLMs).

## The Problem: Which Distribution Should We Use?

When modeling data, we must choose a likelihood function—the probability distribution for our outcome variable. Common choices include:

- Gaussian (normal) for continuous measurements
- Binomial for counts with a known maximum
- Poisson for counts with no clear maximum
- Exponential for waiting times

But *why* these distributions? Are they arbitrary conventions, or is there deeper justification?

## Maximum Entropy: Nature's Favorite Distributions

### The Core Principle

**Maximum entropy** states: Given what we know (constraints), we should choose the distribution that is *most uncertain* (highest entropy) while still satisfying those constraints.

Why? Because any distribution with *lower* entropy would imply we know something we don't actually know. Maximum entropy is maximally honest about our ignorance.

### The Remarkable Result

Different constraints lead to different maximum entropy distributions:

| Constraints | Maximum Entropy Distribution |
|-------------|------------------------------|
| Fixed mean and variance, continuous outcomes | **Gaussian** |
| Binary outcomes, fixed probability | **Binomial** |
| Counts, fixed mean rate | **Poisson** |
| Positive continuous, fixed mean | **Exponential** |
| Positive continuous, fixed mean of log | **Gamma** |

These aren't arbitrary—they're the *least informative* distributions consistent with each set of constraints.

## From Maximum Entropy to GLMs

### The Gaussian Linear Model as a Special Case

The familiar linear regression:

$$Y_i \sim \text{Normal}(\mu_i, \sigma)$$
$$\mu_i = \alpha + \beta X_i$$

This is justified when:
- Outcome is continuous and unbounded
- We only want to constrain mean and variance
- Errors combine additively from many small sources (Central Limit Theorem)

### The GLM Framework

Generalized Linear Models extend regression to other maximum entropy distributions:

$$Y_i \sim \text{Distribution}(\theta_i)$$
$$f(\theta_i) = \alpha + \beta X_i$$

Where:
- **Distribution** is chosen based on outcome type and constraints
- **f()** is the **link function** that connects the linear model to the distribution's parameter

## Link Functions: Why We Need Them

### The Problem

Linear models produce values from -∞ to +∞. But many parameters are constrained:

- Probabilities must be between 0 and 1
- Counts must be non-negative
- Rates must be positive

### The Solution

Link functions **map** the constrained parameter space to the unconstrained linear model space:

| Parameter Constraint | Link Function | Inverse (for interpretation) |
|---------------------|---------------|------------------------------|
| Probability (0,1) | Logit: log(p/(1-p)) | Logistic: 1/(1+e⁻ˣ) |
| Positive (0,∞) | Log: log(λ) | Exponential: eˣ |

### Logit Link in Detail

For binomial/binary outcomes:

$$Y_i \sim \text{Binomial}(n, p_i)$$
$$\text{logit}(p_i) = \alpha + \beta X_i$$

Where logit(p) = log(p/(1-p)), the **log-odds**.

The linear model operates on log-odds (which can be any real number), then the inverse logit transforms back to probability:

$$p_i = \frac{1}{1 + e^{-(\alpha + \beta X_i)}}$$

### Log Link in Detail

For Poisson counts:

$$Y_i \sim \text{Poisson}(\lambda_i)$$
$$\log(\lambda_i) = \alpha + \beta X_i$$

The linear model operates on log-rate, then exponentiation gives the actual rate:

$$\lambda_i = e^{\alpha + \beta X_i}$$

## Interpreting GLM Parameters

### Parameters Are No Longer Additive Effects

This is crucial and often misunderstood.

**In Gaussian regression:** β means "Y changes by β units when X increases by 1"

**In logistic regression:** β means "log-odds change by β when X increases by 1"
- This is NOT a constant change in probability
- The probability change depends on where you start

**In Poisson regression:** β means "log-rate changes by β when X increases by 1"
- Equivalently: rate is multiplied by e^β when X increases by 1
- This is a **proportional** change, not absolute

### Always Visualize on the Outcome Scale

McElreath emphasizes: **Never interpret GLM coefficients from tables alone.**

1. Compute predictions across range of predictors
2. Transform to outcome scale (probability, count, etc.)
3. Plot with uncertainty intervals
4. Report meaningful contrasts (e.g., "probability increases from 0.2 to 0.7")

## Common GLMs and When to Use Them

### Binomial / Logistic Regression

**Outcome:** Counts of successes out of n trials, or binary 0/1

**Maximum entropy justification:** Only constraint is fixed probability of success across trials

**When to use:**
- Binary outcomes (survival, yes/no, pass/fail)
- Proportions with known denominator
- Bounded counts (correct answers out of 10)

**Link:** Logit

### Poisson Regression

**Outcome:** Counts with no theoretical upper bound

**Maximum entropy justification:** Only constraint is fixed mean rate; variance equals mean

**When to use:**
- Event counts (accidents, purchases, species observed)
- Rare events over time or space
- When variance ≈ mean

**Link:** Log

### Dealing with Overdispersion

Real count data often has variance > mean (overdispersion). Options:

**Negative Binomial:** Adds a dispersion parameter
- Maximum entropy distribution when mean varies according to a gamma distribution

**Beta-Binomial:** For proportions with extra-binomial variation
- Probability itself varies according to a beta distribution

## Prior Selection for GLMs

Priors on link scale can imply surprising things on outcome scale:

**Example:** Logistic regression with α ~ Normal(0, 10)

On log-odds scale, this seems weakly informative. But:
- logit⁻¹(10) ≈ 0.99995
- logit⁻¹(-10) ≈ 0.00005

This prior says extreme probabilities near 0 or 1 are plausible—often not what we intend.

**Solution:** Simulate from your priors, transform to outcome scale, and check if the implied predictions make sense.

## Summary Table: GLMs

| Concept | Key Point |
|---------|-----------|
| **Maximum entropy** | Choose the least informative distribution consistent with constraints |
| **GLM** | Extends regression to non-Gaussian outcomes via link functions |
| **Link function** | Maps constrained parameters to unconstrained linear model |
| **Logit link** | For probabilities; operates on log-odds |
| **Log link** | For positive values/rates; operates on log scale |
| **Parameter interpretation** | Not additive on outcome scale; must visualize |
| **Relative vs absolute** | GLM effects are often relative (multiplicative), not absolute |
| **Priors** | Must check implications on outcome scale |

---

# Count Data Models

Chapter 11 ("God Spiked the Integers") dives deeper into **count data models**, addressing the practical complications that arise when the simple Poisson model doesn't fit.

## The Challenge of Count Data

Counts are everywhere:
- Number of tools in a society
- Species observed at a site
- Customer purchases
- Publications by a researcher
- Goals scored in a match

But counts have properties that make them tricky:

1. **Discrete**: Only whole numbers (0, 1, 2, ...)
2. **Bounded below**: Can't go negative
3. **Often bounded above**: Sometimes by exposure, opportunity, or population
4. **Variance linked to mean**: Unlike Gaussian, variance isn't a free parameter

## Poisson Regression Revisited

### The Model

$$Y_i \sim \text{Poisson}(\lambda_i)$$
$$\log(\lambda_i) = \alpha + \beta X_i$$

### Key Property: Mean = Variance

For Poisson, E[Y] = Var[Y] = λ

This is a **strong assumption**. Real data often violates it:
- **Overdispersion**: Variance > Mean (very common)
- **Underdispersion**: Variance < Mean (less common)

### When Poisson Works

- Events are independent
- Rate is constant within observation units
- No unobserved heterogeneity
- No structural zeros

## Exposure and Offset

### The Problem

Different observations may have different "opportunities" for counts:
- Manuscripts per year vs per decade
- Species per 1 km² vs per 100 km²
- Crimes per small town vs large city

Comparing raw counts is misleading when exposure differs.

### The Solution: Offset

Instead of modeling counts directly, model **rates**:

$$Y_i \sim \text{Poisson}(\lambda_i)$$
$$\log(\lambda_i) = \log(\tau_i) + \alpha + \beta X_i$$

Where τᵢ is the exposure (time, area, population, etc.)

The log(τ) term is added to the linear model but **not given a coefficient**—it's fixed at 1. This is called an **offset**.

## Overdispersion: When Variance Exceeds Mean

### Why It Happens

Overdispersion usually indicates **unobserved heterogeneity**—variation in the rate λ that isn't explained by predictors.

Sources include:
- Omitted variables
- Clustering (observations within groups)
- Individual-level variation
- Measurement at wrong scale

### Detecting Overdispersion

Compare observed variance to Poisson-implied variance:

$$\text{Dispersion ratio} = \frac{\text{Observed variance}}{\text{Mean}}$$

- Ratio ≈ 1: Poisson is appropriate
- Ratio >> 1: Overdispersion
- Ratio << 1: Underdispersion

### Consequences of Ignoring Overdispersion

- Standard errors too small
- Confidence/credible intervals too narrow
- False confidence in effects
- Poor predictions for extreme values

## Solutions for Overdispersion

### Option 1: Negative-Binomial (Gamma-Poisson)

The most common solution. Assumes the Poisson rate itself varies according to a Gamma distribution.

**The model:**

$$Y_i \sim \text{NegBinomial}(\mu_i, \phi)$$
$$\log(\mu_i) = \alpha + \beta X_i$$

Where:
- μ is the mean (like λ in Poisson)
- φ (phi) is the **dispersion parameter**

**Variance:** Var[Y] = μ + μ²/φ

- When φ → ∞, variance → μ (approaches Poisson)
- Smaller φ means more overdispersion

### Option 2: Beta-Binomial

For **bounded counts** (successes out of n trials) with overdispersion.

### Option 3: Multilevel Models (Random Effects)

Model the heterogeneity explicitly with varying intercepts:

$$Y_i \sim \text{Poisson}(\lambda_i)$$
$$\log(\lambda_i) = \alpha + \alpha_{group[i]} + \beta X_i$$
$$\alpha_{group} \sim \text{Normal}(0, \sigma)$$

This captures group-level variation that causes overdispersion.

## Multinomial and Categorical Models

### The Setup

Outcome is one of K categories: choice of career, type of event, species identification.

Unlike binomial (two outcomes), we now have K > 2 possible outcomes.

### Maximum Entropy Justification

When outcomes are mutually exclusive and exhaustive with fixed probabilities, the maximum entropy distribution is **Multinomial**.

### Multinomial Logit (Softmax)

Model the **log-odds of each category relative to a baseline**:

$$\Pr(Y = k) = \frac{e^{s_k}}{\sum_{j=1}^{K} e^{s_j}}$$

Where sₖ is the "score" for category k:

$$s_k = \alpha_k + \beta_k X$$

## Summary Table: Count Models

| Model | Use When | Key Feature |
|-------|----------|-------------|
| **Poisson** | Counts, variance ≈ mean | Simplest count model |
| **Poisson with offset** | Counts with varying exposure | Models rates, not raw counts |
| **Negative-Binomial** | Overdispersed counts | Adds dispersion parameter φ |
| **Beta-Binomial** | Overdispersed bounded counts | Probability varies by observation |
| **Multinomial** | Categorical outcomes K > 2 | Multiple discrete choices |

## Practical Workflow

1. **Examine your counts**: Mean, variance, zeros, max values
2. **Start with Poisson**: The baseline count model
3. **Check for overdispersion**: Posterior predictive checks, variance ratio
4. **If overdispersed**: Try Negative-Binomial or multilevel
5. **Consider exposure**: Do observations have equal opportunity?
6. **Always visualize**: Predictions on count scale with uncertainty
7. **Compare models**: WAIC/PSIS-LOO for predictive accuracy

---

# Monsters and Mixtures

Chapter 12 tackles the **strange creatures** that arise when standard models don't fit—outcomes that are ordered but not metric, data with too many zeros, and situations where observations come from multiple different processes.

## The Monsters

1. **Ordered categories**: Ratings (1-5 stars), education levels, Likert scales
2. **Zero-inflated counts**: More zeros than Poisson predicts
3. **Zero-inflated continuous**: Many exact zeros plus continuous positive values
4. **Mixtures of processes**: Data generated by multiple distinct mechanisms

## Ordered Categorical Outcomes

### The Problem

Consider a survey response: "Rate your satisfaction from 1 to 5."

**Why not treat as continuous?**
- The gaps between categories may not be equal
- It's fundamentally discrete

**Why not treat as unordered categorical (multinomial)?**
- Ignores the ordering information
- Wastes valuable information

### The Solution: Cumulative Link Models (Ordered Logit/Probit)

Model the **cumulative probability** of being at or below each category.

**The intuition:** Imagine a latent continuous variable that gets "cut" into categories by thresholds.

### The Mathematical Model

For K ordered categories, we have K-1 cutpoints (α₁, α₂, ..., αₖ₋₁).

**Cumulative probability:**
$$\Pr(Y_i \leq k) = \frac{1}{1 + e^{-(\alpha_k - \phi_i)}}$$

Where φᵢ is the linear model (without its own intercept—the cutpoints serve that role):
$$\phi_i = \beta_1 X_{1i} + \beta_2 X_{2i} + ...$$

**Category probability:**
$$\Pr(Y_i = k) = \Pr(Y_i \leq k) - \Pr(Y_i \leq k-1)$$

### Interpreting Predictor Effects

A positive β **shifts probability toward higher categories**.

But the effect isn't uniform:
- Near the middle categories: larger probability shifts
- Near extremes: smaller probability shifts (floor/ceiling effects)

**Always visualize:** Plot predicted category probabilities across predictor range.

## Zero-Inflated Models

### The Problem

Many count datasets have **more zeros than expected**:
- Days with zero purchases
- Species counts at sites
- Manuscript submissions

**Two types of zeros:**
1. **Structural zeros**: Zeros that *must* occur (site has no habitat)
2. **Sampling zeros**: Zeros by chance from the count process

### Zero-Inflated Poisson (ZIP)

**The story:** Two processes generate data:
1. With probability p: always zero (structural)
2. With probability 1-p: Poisson process (may be zero by chance)

**The likelihood:**

$$\Pr(Y = 0) = p + (1-p) \cdot e^{-\lambda}$$

$$\Pr(Y = k) = (1-p) \cdot \frac{\lambda^k e^{-\lambda}}{k!} \quad \text{for } k > 0$$

**Two linear models:**
$$\text{logit}(p_i) = \alpha_p + \beta_p X_i \quad \text{(probability of structural zero)}$$
$$\log(\lambda_i) = \alpha_\lambda + \beta_\lambda X_i \quad \text{(Poisson rate when not structural zero)}$$

### Interpretation

- **p**: Probability observation comes from "always zero" process
- **λ**: Rate of counts *among observations that can have counts*
- **Predictors can affect both**

## Zero-Inflated Continuous (Hurdle Models)

### The Problem

Some continuous outcomes have many exact zeros:
- Medical costs
- Rainfall
- Time spent on activity

### The Solution: Hurdle Model

Two-part model:
1. **Binary process**: Did the event occur at all? (logistic)
2. **Continuous process**: Given it occurred, how much? (Gamma, log-normal, etc.)

## Mixture Models More Generally

### The Core Idea

Sometimes data comes from **multiple distinct processes**, and we don't know which process generated each observation.

**General mixture:**
$$\Pr(Y = y) = \sum_{k=1}^{K} \pi_k \cdot f_k(y | \theta_k)$$

Where:
- πₖ is the probability of belonging to component k
- fₖ is the distribution for component k
- θₖ are the parameters for component k

### Identification Challenges

Mixture models can be **weakly identified**:
- Multiple parameter combinations may produce similar likelihoods
- Components can "swap" labels across MCMC iterations
- Need informative priors or constraints

## Ordered Predictors

### The Problem

What about ordered categorical **predictors**?

### Why Not Just Use Dummy Variables?

- Ignores ordering
- No borrowing of information between adjacent levels

### Why Not Just Use Numeric Codes (1, 2, 3, 4, 5)?

- Assumes equal spacing

### The Solution: Monotonic Effects

Estimate a **total effect** and **simplex of proportions** for how that effect is distributed across transitions.

## Summary Table: Monsters and Mixtures

| Monster | Problem | Solution | Key Feature |
|---------|---------|----------|-------------|
| **Ordered categories** | Discrete ordered outcome | Cumulative logit | Cutpoints define category boundaries |
| **Zero-inflated counts** | Excess zeros in counts | ZIP / ZINB | Two processes: always-zero + count |
| **Zero-inflated continuous** | Exact zeros + positive continuous | Hurdle model | Binary occurrence + continuous amount |
| **Finite mixtures** | Multiple generating processes | Mixture model | Latent component membership |
| **Ordered predictors** | Categorical predictor with order | Monotonic effects | Simplex over transitions |

## The Deeper Lesson

Each "monster" model tells a **scientific story**:
- Ordered categorical: "There's a latent continuum that we only observe in chunks"
- Zero-inflated: "Two different mechanisms can produce zeros"
- Hurdle: "First decide if it happens, then how much"
- Mixture: "The population contains distinct subgroups"

**The story must be scientifically plausible.**

---

# Multilevel Models

Chapter 13 ("Models with Memory") introduces **multilevel models** (also called hierarchical models, random effects models, or mixed effects models).

## The Core Problem: Clustered Data

Data often comes in **clusters**:
- Students within schools
- Patients within hospitals
- Observations within individuals (repeated measures)
- Species within genera

Observations within the same cluster are not independent—they share unmeasured influences.

## Two Bad Options (Before Multilevel)

### Option 1: Complete Pooling

Ignore the clusters entirely. Estimate one set of parameters for all data.

**Problem:** 
- Assumes all clusters are identical
- Underestimates uncertainty
- Ignores real variation between clusters

### Option 2: No Pooling

Estimate completely separate parameters for each cluster.

**Problems:**
- Overfits clusters with few observations
- Learns nothing from other clusters
- Extreme estimates for small samples
- Can't predict for new clusters

## The Multilevel Solution: Partial Pooling

Multilevel models find the **sweet spot** between complete pooling and no pooling.

**The key idea:** Cluster parameters come from a common distribution.

$$Y_i \sim \text{Normal}(\mu_i, \sigma)$$
$$\mu_i = \alpha_{cluster[i]} + \beta X_i$$
$$\alpha_{cluster} \sim \text{Normal}(\bar{\alpha}, \sigma_\alpha)$$

Now:
- Each cluster has its own intercept αₖ
- But these intercepts are **connected** through the hyperparameters (ᾱ, σ_α)
- Clusters inform each other

### What Partial Pooling Does

**Shrinkage:** Extreme cluster estimates are pulled toward the global mean.

- Clusters with lots of data: estimates stay close to their raw values
- Clusters with little data: estimates shrink toward global mean
- The amount of shrinkage is learned from the data

**Adaptive regularization:** The model learns how much variation exists between clusters (σ_α) and uses this to calibrate shrinkage.

## The Multilevel Model Structure

### The Hierarchy

```
Level 3: Hyperpriors (priors on σ_α, ᾱ)
    ↓
Level 2: Population distribution of cluster parameters
    ↓
Level 1: Observations within clusters
```

Information flows **both directions**:
- Down: Population distribution constrains cluster estimates
- Up: Cluster data informs population distribution

## Why Multilevel Models Are Better

### 1. Improved Predictions

Out-of-sample prediction is almost always better than no-pooling because:
- Extreme estimates from small samples are unreliable
- Shrinkage provides automatic regularization

### 2. Honest Uncertainty

- Uncertainty about hyperparameters propagates to cluster estimates
- Clusters with little data have wider intervals

### 3. Predictions for New Clusters

With no-pooling, you can't predict for a new cluster. With multilevel:
$$\alpha_{new} \sim \text{Normal}(\bar{\alpha}, \sigma_{café})$$

### 4. Learning Across Clusters

Each cluster contributes to learning the population mean and variation.

## Multiple Levels of Clustering

### Nested Example
Students within classrooms within schools:

$$\text{Score}_{ijk} \sim \text{Normal}(\mu_{ijk}, \sigma)$$
$$\mu_{ijk} = \alpha + \alpha_{school[j]} + \alpha_{classroom[k]} + \beta X_{ijk}$$

### Crossed Example
Products rated by customers (not nested):

$$\text{Rating}_{ij} \sim \text{Normal}(\mu_{ij}, \sigma)$$
$$\mu_{ij} = \alpha + \alpha_{customer[i]} + \alpha_{product[j]}$$

## Varying Effects Beyond Intercepts

**Varying intercepts:** Each cluster has its own baseline.

**Varying slopes:** Each cluster has its own effect of X.

$$\mu_i = \alpha_{cluster[i]} + \beta_{cluster[i]} X_i$$
$$\begin{bmatrix} \alpha_{cluster} \\ \beta_{cluster} \end{bmatrix} \sim \text{MVNormal}\left(\begin{bmatrix} \bar{\alpha} \\ \bar{\beta} \end{bmatrix}, \Sigma\right)$$

## Divergent Transitions and the Centered Parameterization Problem

### The Problem

Multilevel models often produce **divergent transitions** in MCMC.

### The Non-Centered Parameterization

**Centered (problematic):**
$$\alpha_{cluster} \sim \text{Normal}(\bar{\alpha}, \sigma_\alpha)$$

**Non-centered (better):**
$$z_{cluster} \sim \text{Normal}(0, 1)$$
$$\alpha_{cluster} = \bar{\alpha} + z_{cluster} \cdot \sigma_\alpha$$

Mathematically identical, but the sampler works on z (standardized deviations).

## Summary Table: Multilevel Models

| Approach | Description | When to Use |
|----------|-------------|-------------|
| **Complete pooling** | Ignore clusters | Never (almost) |
| **No pooling** | Separate estimates per cluster | When clusters have tons of data |
| **Partial pooling** | Connected through population distribution | Default for clustered data |
| **Varying intercepts** | Each cluster has own baseline | Clusters differ in level |
| **Varying slopes** | Each cluster has own effect | Effect of X differs by cluster |
| **Non-centered** | Reparameterize for sampling | When you get divergences |

## The Big Picture

McElreath argues multilevel models should be the **default**, not the exception:

> "Multilevel regression deserves to be the default form of regression."

---

# Covariance and Gaussian Processes

Chapter 14 ("Adventures in Covariance") extends multilevel models to handle **correlated varying effects** and introduces **Gaussian processes**.

## The Core Problem: Correlated Varying Effects

When clusters have both varying intercepts and varying slopes, these often covary—and modeling that covariance improves inference.

## Varying Slopes: The Full Model

### The Multivariate Normal Prior

Model intercepts and slopes **jointly**:

$$\begin{bmatrix} \alpha_{café} \\ \beta_{café} \end{bmatrix} \sim \text{MVNormal}\left(\begin{bmatrix} \bar{\alpha} \\ \bar{\beta} \end{bmatrix}, \mathbf{S}\right)$$

Where **S** is the covariance matrix:

$$\mathbf{S} = \begin{bmatrix} \sigma^2_\alpha & \rho \sigma_\alpha \sigma_\beta \\ \rho \sigma_\alpha \sigma_\beta & \sigma^2_\beta \end{bmatrix}$$

**Components:**
- σ²_α: Variance of intercepts across clusters
- σ²_β: Variance of slopes across clusters
- ρ: Correlation between intercepts and slopes

## What the Correlation Tells Us

### Positive Correlation (ρ > 0)
Clusters with higher intercepts tend to have higher slopes.

### Negative Correlation (ρ < 0)
Clusters with higher intercepts tend to have lower slopes.

### Near-Zero Correlation (ρ ≈ 0)
Intercepts and slopes vary independently.

## The Decomposition: Variances and Correlations

Decompose **S** into:

1. **Standard deviations** (σ_α, σ_β)
2. **Correlation matrix** (R)

$$\mathbf{S} = \text{diag}(\boldsymbol{\sigma}) \cdot \mathbf{R} \cdot \text{diag}(\boldsymbol{\sigma})$$

### Priors for Correlation Matrix

- LKJ distribution
- Parameter η controls concentration:
  - η = 1: Uniform over valid correlation matrices
  - η > 1: Skeptical of extreme correlations

## Non-Centered Parameterization for Varying Slopes

Use Cholesky decomposition:
$$\begin{bmatrix} \alpha_j \\ \beta_j \end{bmatrix} = \begin{bmatrix} \bar{\alpha} \\ \bar{\beta} \end{bmatrix} + \mathbf{L} \begin{bmatrix} z_{\alpha,j} \\ z_{\beta,j} \end{bmatrix}$$

Where **L** is the Cholesky factor of **S**.

## Gaussian Processes

### The Core Idea

Instead of discrete clusters, what if similarity is **continuous**?

GPs model this with a **covariance function** (kernel) that defines how similarity decays with distance.

### The GP Model

$$\mathbf{Y} \sim \text{MVNormal}(\boldsymbol{\mu}, \mathbf{K})$$

Where **K** is a covariance matrix with entries:

$$K_{ij} = k(d_{ij})$$

### Common Kernels

**Squared exponential (RBF):**
$$k(d) = \eta^2 \exp\left(-\frac{d^2}{2\ell^2}\right)$$

- η²: Maximum covariance (at d = 0)
- ℓ: Lengthscale (how quickly correlation decays)

**Ornstein-Uhlenbeck (exponential):**
$$k(d) = \eta^2 \exp\left(-\frac{d}{\ell}\right)$$

### Phylogenetic Regression

Species that share recent common ancestors should have similar traits.

**The covariance:** Derived from phylogenetic tree (time since divergence).

## Summary Table: Covariance

| Concept | Purpose | Key Feature |
|---------|---------|-------------|
| **Varying slopes** | Different effects per cluster | Each cluster gets own β |
| **Covariance matrix** | Model correlation between varying effects | Captures intercept-slope relationship |
| **LKJ prior** | Prior on correlation matrix | η parameter controls regularization |
| **Gaussian process** | Continuous covariance structure | Kernel defines similarity decay |
| **Lengthscale (ℓ)** | GP parameter | How far correlation extends |

---

# Missing Data

Chapter 15 ("Missing Data and Other Opportunities") reframes **missing data** not as a nuisance but as an opportunity.

## Why Data Are Missing: The Taxonomy

### Missing Completely at Random (MCAR)

Missingness is unrelated to any variables.

**Consequence:** Complete case analysis is unbiased (but loses power).

### Missing at Random (MAR)

Missingness depends on **observed** variables but not on the missing values themselves.

**Consequence:** Can recover unbiased estimates if we condition on variables that predict missingness.

### Missing Not at Random (MNAR)

Missingness depends on the **missing values themselves**.

**Consequence:** Most problematic. Cannot fully correct without modeling the missingness mechanism.

## The DAG Approach to Missing Data

### Four Archetypal Patterns

**Pattern 1: Dog eats random homework (MCAR)**
```
X → Y
(R independent)
```

**Pattern 2: Dog targets students (MAR)**
```
S → Y
S → R_Y
```

**Pattern 3: Dog eats bad homework (MNAR)**
```
S → H → R_H
```

**Pattern 4: Unobserved confounder (MNAR)**
```
U → Y
U → R_Y
```

## The Bayesian Solution: Imputation as Inference

### The Key Insight

Missing values are just **unknown parameters**. Bayesian inference handles unknowns naturally:

$$P(\theta, Y_{miss} | Y_{obs}) \propto P(Y_{obs}, Y_{miss} | \theta) P(\theta)$$

### How It Works

1. Specify a model for the complete data
2. Treat missing values as parameters with priors
3. Sample from the joint posterior
4. Each posterior sample includes imputed values

**Result:** Uncertainty about missing values propagates to all inferences.

## Discrete Missing Values: Marginalization

Sum over all possible values of the missing discrete variable:

$$P(Y_i | X_i \text{ missing}) = P(Y_i | X_i = 0) P(X_i = 0) + P(Y_i | X_i = 1) P(X_i = 1)$$

## Measurement Error

### The Problem

We observe X (with error), not X* (true value):
$$X_i = X_i^* + \delta_i$$

Naive regression biases β toward zero (attenuation).

### The Bayesian Solution

Model the true X* as a latent variable:

$$X_i^* \sim \text{Normal}(\mu_X, \sigma_X)$$
$$X_i \sim \text{Normal}(X_i^*, \sigma_{error})$$
$$Y_i \sim \text{Normal}(\alpha + \beta X_i^*, \sigma_Y)$$

## Censored and Truncated Data

### Censoring

We know a value exists beyond a threshold but not its exact value.

For right-censored Y at threshold τ:
- Observed: normal likelihood
- Censored: survival probability P(Y > τ)

### Truncation

Observations beyond the threshold aren't even in the dataset.

**Solution:** Renormalize the likelihood.

## Summary Table: Missing Data

| Concept | Description | Key Approach |
|---------|-------------|--------------|
| **MCAR** | Missingness unrelated to any variables | Complete cases OK |
| **MAR** | Missingness depends on observed variables | Condition on predictors |
| **MNAR** | Missingness depends on missing values | Model missingness mechanism |
| **Bayesian imputation** | Treat missing values as parameters | Joint posterior |
| **Marginalization** | For discrete missing values | Sum over possible values |
| **Measurement error** | Observed ≠ true value | Model latent true values |
| **Censoring** | Know value beyond threshold | Survival probability likelihood |

---

# Custom Likelihoods

Chapter 16 ("Generalized Linear Madness") pushes beyond standard GLMs into **custom likelihood functions**.

## The Limits of Standard GLMs

Real data often doesn't fit standard distributions:
- Outcomes with complex constraints
- Multiple simultaneous processes
- Custom scientific models
- Mechanistic theories

**The solution:** Build the likelihood function your science demands.

## Geometric and Negative-Binomial for Events

### The Geometric Distribution

**The question:** How many failures before the first success?

$$Y \sim \text{Geometric}(p)$$
$$P(Y = k) = (1-p)^k \cdot p$$

## The Exponential and Gamma for Continuous Time

### Exponential Distribution

Time until an event, assuming constant hazard rate.

$$Y \sim \text{Exponential}(\lambda)$$
$$f(y) = \lambda e^{-\lambda y}$$

### Gamma Distribution

Time until the k-th event in a Poisson process.

## Beta Regression: Proportions Without Bounds

### The Problem

Proportions between 0 and 1 that aren't counts.

### The Solution

$$Y_i \sim \text{Beta}(\mu_i \phi, (1-\mu_i)\phi)$$
$$\text{logit}(\mu_i) = \alpha + \beta X_i$$

## Custom Likelihoods: The General Principle

### The Bayesian Recipe

1. **Define the generative process:** How does nature produce your data?
2. **Write the probability function:** P(data | parameters)
3. **Specify priors:** P(parameters)
4. **Compute posterior**

## Differential Equation Models

### The Structure

**Deterministic dynamics:**
$$\frac{dY}{dt} = f(Y, t, \theta)$$

**With observation error:**
$$Y_{obs,t} \sim \text{Normal}(Y_t, \sigma)$$

### Example: SIR Epidemic Model

$$\frac{dS}{dt} = -\beta S I$$
$$\frac{dI}{dt} = \beta S I - \gamma I$$
$$\frac{dR}{dt} = \gamma I$$

## Occupancy Models

### The Two-Process Model

1. **Occupancy process:** Is the species truly present?
$$Z_i \sim \text{Bernoulli}(\psi_i)$$

2. **Detection process:** Given presence, do we detect it?
$$Y_{ij} | Z_i = 1 \sim \text{Bernoulli}(p_{ij})$$

## Survival Analysis: Hazard Models

### The Hazard Function

$$h(t) = \lim_{\Delta t \to 0} \frac{P(t \leq T < t + \Delta t | T \geq t)}{\Delta t}$$

### Proportional Hazards

$$h(t | X) = h_0(t) \exp(\beta X)$$

## Summary Table: Custom Models

| Model Type | Use Case | Key Feature |
|------------|----------|-------------|
| **Geometric/Negative-Binomial** | Waiting times (discrete) | Trials until success |
| **Exponential/Gamma** | Waiting times (continuous) | Time until event(s) |
| **Beta regression** | Proportions in (0,1) | Bounded continuous |
| **ODE models** | Dynamic systems | Mechanistic process |
| **Phylogenetic regression** | Cross-species comparisons | Evolutionary non-independence |
| **HMM/State space** | Latent states over time | Hidden process |
| **Occupancy models** | Presence/absence with imperfect detection | Separate occupancy from detection |
| **Survival/Hazard** | Time-to-event with censoring | Handle incomplete observations |

---

# Model Comparison and Criticism

Chapter 17 ("Horoscopes") addresses **model comparison and criticism**—how to evaluate whether your model is any good.

## The Horoscope Warning

Models can seem to explain everything while actually predicting nothing useful.

**Statistical models can have the same problem:**
- Complex models fit training data beautifully
- But may capture noise, not signal
- Predictions for new data are poor

## Posterior Predictive Checks

### The Basic Idea

If your model is good, **data simulated from it should resemble real data.**

**Procedure:**
1. Draw parameter values from posterior
2. Simulate new data using those parameters
3. Compare simulated data to observed data
4. Look for systematic discrepancies

### What to Compare

- Mean, variance, skewness
- Minimum, maximum, range
- Proportion of zeros
- Shape of distribution
- Correlations, patterns

## WAIC: Widely Applicable Information Criterion

### The Formula

$$\text{WAIC} = -2 \left( \text{lppd} - p_{WAIC} \right)$$

Where p_WAIC is the **effective number of parameters:**

$$p_{WAIC} = \sum_{i=1}^{N} \text{Var}_{\theta} \left[ \log P(y_i | \theta) \right]$$

### Interpreting WAIC

- Lower WAIC = better expected out-of-sample prediction
- Differences matter more than absolute values

## PSIS-LOO: Pareto-Smoothed Importance Sampling Leave-One-Out

### The Pareto k Diagnostic

- k̂ < 0.5: Excellent, reliable estimate
- 0.5 < k̂ < 0.7: Good, some uncertainty
- 0.7 < k̂ < 1: Problematic, high variance
- k̂ > 1: Very bad, estimate unreliable

## Comparing Models

### The Comparison Table

```
       WAIC    SE    dWAIC   dSE   pWAIC  weight
m1    312.4   15.2    0.0    -     4.2    0.72
m2    315.1   14.8    2.7    3.1   5.1    0.19
m3    318.6   16.1    6.2    4.5   7.3    0.09
```

### Interpreting Differences

- dWAIC >> dSE: Meaningful difference
- dWAIC ≈ dSE: Uncertain which is better
- dWAIC << dSE: Models essentially equivalent

### Model Weights (Akaike Weights)

$$w_i = \frac{\exp(-\frac{1}{2} \Delta_i)}{\sum_j \exp(-\frac{1}{2} \Delta_j)}$$

## Model Averaging

### The Problem with Model Selection

Choosing the "best" model ignores:
- Uncertainty about which model is best
- Information in other models

### Stacking Weights

Optimize weights to minimize LOO prediction error.

## Causal Inference vs Prediction

### The Fundamental Tension

**Predictive accuracy (WAIC/LOO):**
- Which model predicts best?
- May favor confounded models!

**Causal accuracy:**
- Which model estimates causal effects correctly?
- Requires correct adjustment set (from DAG)

### The Lesson

**WAIC/LOO tells you about prediction, not causation.**

- Use DAGs for causal inference
- Use WAIC/LOO for prediction
- They can disagree!

## The Failures of R²

### Why R² Misleads

1. Always increases with complexity
2. Doesn't measure prediction
3. Scale-dependent
4. Ignores uncertainty

### Better Alternatives

- **WAIC/LOO:** Directly estimates predictive accuracy
- **Posterior predictive checks:** Visual assessment
- **Effect sizes:** Scientifically meaningful quantities

## Summary Table: Model Criticism

| Tool | Purpose | Interpretation |
|------|---------|----------------|
| **Posterior predictive check** | Does model capture data features? | Visual/statistical comparison |
| **WAIC** | Estimated out-of-sample deviance | Lower is better |
| **p_WAIC** | Effective number of parameters | Measures flexibility used |
| **PSIS-LOO** | More robust than WAIC | Lower is better |
| **Pareto k̂** | Reliability of LOO estimate | k̂ > 0.7 is problematic |
| **Model weights** | Relative predictive performance | Sum to 1, higher is better |

## Workflow for Model Criticism

1. **Prior Predictive Check:** Simulate from priors
2. **Fit Model:** Check convergence
3. **Posterior Predictive Check:** Compare simulated to observed
4. **Compute Information Criteria:** WAIC and/or PSIS-LOO
5. **Compare Models:** If multiple models
6. **Sensitivity Analysis:** Different priors, excluding points

---

# Key Themes Across All Chapters

## 1. DAGs Are Essential

Every modeling decision should be guided by your causal model:
- What to include
- What to exclude
- How to interpret results

## 2. Maximum Entropy Guides Distribution Choice

Choose distributions that assume the least beyond your stated constraints.

## 3. Prediction ≠ Causation

- WAIC/LOO measure prediction
- DAGs guide causal inference
- They answer different questions

## 4. Always Visualize

- Never interpret coefficients from tables alone
- Plot predictions on outcome scale
- Include uncertainty

## 5. Embrace Uncertainty

- Wide posteriors are honest, not failures
- Propagate uncertainty through all analyses
- Report full distributions, not just point estimates

## 6. Models Are Tools, Not Truth

> "All models are wrong, but some are useful." — George Box

The goal is useful understanding and prediction, not finding "the true model."

---

# Quick Reference: Choosing Methods

| Data Type | Standard Approach | Consider If... |
|-----------|-------------------|----------------|
| Continuous outcome | Gaussian | Bounded → Beta; Positive → Gamma |
| Binary outcome | Binomial/Logistic | - |
| Counts (no upper bound) | Poisson | Overdispersed → Neg-Binomial; Excess zeros → ZIP |
| Counts (bounded) | Binomial | Overdispersed → Beta-Binomial |
| Ordered categories | Ordered Logit | - |
| Multiple categories | Multinomial | - |
| Clustered data | Multilevel | Always consider varying slopes |
| Spatial/temporal correlation | Gaussian Process | - |
| Missing data | Bayesian imputation | MNAR → Model mechanism |
| Waiting times | Exponential/Gamma | Discrete → Geometric |

---

# Resources

- **Book:** McElreath, R. (2020). *Statistical Rethinking: A Bayesian Course with Examples in R and Stan* (2nd ed.)
- **Python implementations:** [pymc-devs/pymc-resources](https://github.com/pymc-devs/pymc-resources)
- **Lectures:** Available on YouTube
- **Stan documentation:** [mc-stan.org](https://mc-stan.org)
- **PyMC documentation:** [docs.pymc.io](https://docs.pymc.io)
