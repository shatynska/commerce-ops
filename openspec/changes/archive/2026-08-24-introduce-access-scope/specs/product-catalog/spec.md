## MODIFIED Requirements

### Requirement: A product can be read back by identifier or by SKU

The system SHALL retrieve a registered product — identity, name, current stage, and stage-entry time — given either its product identifier or its SKU, together with the caller's access scope, and SHALL return the product only when the scope permits its product identifier. When no product matches, or a matching product is outside the caller's scope, the system SHALL report absence rather than an error — an out-of-scope product is indistinguishable from one that does not exist, so a read can never confirm the existence of a product the caller may not see.

#### Scenario: A product is retrieved by identifier

- **WHEN** a product is read using the identifier it was registered with, under a scope that permits that identifier
- **THEN** the product is returned with every field it carries

#### Scenario: A product is retrieved by SKU

- **WHEN** a product is read using its SKU, under a scope that permits its product identifier
- **THEN** the same product is returned

#### Scenario: An unknown product reports absence

- **WHEN** a product is read using an identifier or SKU no registered product has, under any scope
- **THEN** the system reports that no product was found, rather than an error

#### Scenario: An out-of-scope product reports the same absence

- **WHEN** a registered product is read by identifier or by SKU under a scope that does not permit its product identifier
- **THEN** the system reports that no product was found, exactly as it does for a product that does not exist

### Requirement: Products can be listed with their stages

The system SHALL list registered products with, at minimum, each product's identifier, SKU, name, and current lifecycle stage, filtered by the caller's access scope: only products whose identifier the scope permits SHALL appear, an unrestricted scope SHALL list every registered product, and the system SHALL report an empty result rather than an error when no product exists or none is in scope.

#### Scenario: Products are listed

- **WHEN** the product list is requested under the unrestricted scope and products exist
- **THEN** every registered product is returned with its identifier, SKU, name, and current stage

#### Scenario: A restricted scope lists only its products

- **WHEN** the product list is requested under a scope permitting some registered products' identifiers but not others
- **THEN** exactly the permitted products are returned

#### Scenario: An empty catalog lists nothing

- **WHEN** the product list is requested and no products exist
- **THEN** an empty result is returned

#### Scenario: A scope permitting nothing lists nothing

- **WHEN** the product list is requested under a scope that permits no product identifier and products exist
- **THEN** an empty result is returned rather than an error
